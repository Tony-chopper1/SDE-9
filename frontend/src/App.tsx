import React, { useEffect, useRef, useState } from 'react';
import { TranscriptTimeline } from './components/TranscriptTimeline';
import { TranscriptSegment } from './api_client';

type RecordingSession = {
  id: string;
  date: string;
  transcript: string;
};

export const App: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState('');

  const [recordingHistory, setRecordingHistory] =
    useState<RecordingSession[]>([]);

  const [selectedSessionId, setSelectedSessionId] =
    useState<string | null>(null);

  const recognitionRef = useRef<any>(null);
  const finalTranscriptRef = useRef('');
  const transcriptTextRef = useRef('');

  const historyRef = useRef<RecordingSession[]>([]);
  const shouldSaveSessionRef = useRef(false);
  const sessionSavedRef = useRef(false);

  const [segments] = useState<TranscriptSegment[]>([
    {
      id: 'demo-1',
      text: 'SDK-9 AI Voice Co-Pilot active.',
      confidence: 0.99,
      start_time: 0,
      end_time: 1.5,
      is_final: true,
    },
  ]);

  // Microphone recording references
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Error message
  const [errorMessage, setErrorMessage] = useState('');

  // Load recording history when app opens
  useEffect(() => {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        return;
      }

      const savedHistory = window.localStorage.getItem(
        'echo-recording-history'
      );

      if (savedHistory) {
        const parsedHistory = JSON.parse(savedHistory);
        historyRef.current = parsedHistory;
        setRecordingHistory(parsedHistory);
      }
    } catch (error) {
      console.error('Unable to load recording history:', error);
    }
  }, []);

  // Selected previous recording
  const selectedSession = recordingHistory.find(
    (session) => session.id === selectedSessionId
  );

  const displayedTranscript = selectedSession
    ? selectedSession.transcript
    : liveTranscript;

  // Save a completed transcript
  const saveSession = (transcript: string) => {
    const cleanedTranscript = transcript.trim();

    if (!cleanedTranscript || sessionSavedRef.current) {
      return;
    }

    const newSession: RecordingSession = {
      id: Date.now().toString(),
      date: new Date().toLocaleString(),
      transcript: cleanedTranscript,
    };

    const updatedHistory = [newSession, ...historyRef.current];

    historyRef.current = updatedHistory;
    sessionSavedRef.current = true;

    setRecordingHistory(updatedHistory);
    setSelectedSessionId(newSession.id);

    try {
      localStorage.setItem(
        'echo-recording-history',
        JSON.stringify(updatedHistory)
      );

      console.log('Recording history saved:', newSession);
    } catch (error) {
      console.error('Unable to save recording history:', error);
      setErrorMessage('Could not save history in browser storage.');
    }
  };

  // Start microphone recording and speech recognition
  const startRecording = async () => {
    try {
      setErrorMessage('');
      setLiveTranscript('');
      finalTranscriptRef.current = '';
      transcriptTextRef.current = '';

      sessionSavedRef.current = false;
      shouldSaveSessionRef.current = false;
      setSelectedSessionId(null);

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          'Microphone access is not supported in this browser.'
        );
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      // Start audio recording
      const recorder = new MediaRecorder(stream);

      audioChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });

        console.log('Recording completed:', audioBlob);
        console.log('Audio size:', audioBlob.size, 'bytes');

        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorderRef.current = recorder;
      recorder.start();

      setIsRecording(true);

      // Check browser speech recognition support
      const SpeechRecognition =
        (window as any).SpeechRecognition ||
        (window as any).webkitSpeechRecognition;

      if (!SpeechRecognition) {
        setErrorMessage(
          'Speech recognition is not supported. Audio recording is still active.'
        );
        return;
      }

      // Create speech recognition instance
      const recognition = new SpeechRecognition();

      recognition.lang = 'en-IN';
      recognition.continuous = true;
      recognition.interimResults = true;

      // Handle recognized speech
      recognition.onresult = (event: any) => {
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;

          if (event.results[i].isFinal) {
            finalTranscriptRef.current += transcript + ' ';
          } else {
            interimTranscript += transcript;
          }
        }

        const updatedTranscript =
          finalTranscriptRef.current + interimTranscript;

        transcriptTextRef.current = updatedTranscript;
        setLiveTranscript(updatedTranscript);
      };

      // Handle speech recognition errors
      recognition.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);

        setErrorMessage(
          `Speech recognition error: ${event.error}. Check microphone permission and internet connection.`
        );
      };

      // Save transcript when recognition finishes after Stop
      recognition.onend = () => {
        console.log('Speech recognition ended.');

        if (shouldSaveSessionRef.current) {
          saveSession(transcriptTextRef.current);
          shouldSaveSessionRef.current = false;
        }

        recognitionRef.current = null;
      };

      recognitionRef.current = recognition;

      try {
        recognition.start();
        console.log('Live speech recognition started.');
      } catch (recognitionError) {
        console.error('Unable to start speech recognition:', recognitionError);

        recognitionRef.current = null;

        setErrorMessage(
          'Speech recognition could not start. Audio recording is still active.'
        );
      }
    } catch (error) {
      console.error('Microphone error:', error);

      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to access microphone. Please allow microphone permission.'
      );

      setIsRecording(false);
    }
  };

  // Stop recording and save transcript
  const stopRecording = () => {
    const recognition = recognitionRef.current;

    if (recognition) {
      shouldSaveSessionRef.current = true;

      try {
        recognition.stop();
      } catch (error) {
        console.error('Speech recognition stop error:', error);

        shouldSaveSessionRef.current = false;
        saveSession(transcriptTextRef.current);
      }
    } else {
      saveSession(transcriptTextRef.current);
    }

    // Stop audio recording
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state === 'recording'
    ) {
      mediaRecorderRef.current.stop();
    }

    setIsRecording(false);
  };

  // Download the current or selected transcript
  const downloadTranscript = () => {
    const transcript = displayedTranscript.trim();

    if (!transcript) {
      setErrorMessage('There is no transcript available to download.');
      return;
    }

    const blob = new Blob([transcript], {
      type: 'text/plain;charset=utf-8',
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = `echo-transcript-${Date.now()}.txt`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  };

  // Delete a saved recording
  const deleteSession = (sessionId: string) => {
    const updatedHistory = historyRef.current.filter(
      (session) => session.id !== sessionId
    );

    historyRef.current = updatedHistory;
    setRecordingHistory(updatedHistory);

    try {
      localStorage.setItem(
        'echo-recording-history',
        JSON.stringify(updatedHistory)
      );

      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
      }

      console.log('Recording deleted successfully.');
    } catch (error) {
      console.error('Unable to delete recording:', error);
      setErrorMessage('Unable to delete recording.');
    }
  };

  return (
    <main className="echo-app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">E</div>
          <div>
            <h2>ECHO<span>AI</span></h2>
            <small>VOICE INTELLIGENCE</small>
          </div>
        </div>

        <div className="side-label">WORKSPACE</div>

        <div
          className="nav-item active"
          onClick={() => setSelectedSessionId(null)}
        >
          <span>◉</span> Voice Studio
        </div>

        <div
          className="nav-item"
          onClick={() => {
            if (recordingHistory.length > 0) {
              setSelectedSessionId(recordingHistory[0].id);
            }
          }}
        >
          <span>▤</span> Transcripts
        </div>

        <div
          className="nav-item"
          onClick={() => {
            if (recordingHistory.length > 0) {
              setSelectedSessionId(recordingHistory[0].id);
            }
          }}
        >
          <span>◷</span> Recording History
        </div>

        <div className="sidebar-bottom">
          <div className="profile-avatar">S</div>
          <div>
            <strong>SDK-9 Workspace</strong>
            <small>Personal workspace</small>
          </div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div>
            <span className="breadcrumb">WORKSPACE / VOICE STUDIO</span>
            <h1>Voice Studio</h1>
          </div>

          <div className="connection">
            <span className="status-dot"></span>
            SYSTEM READY
          </div>
        </header>

        <section className="welcome">
          <div>
            <span className="eyebrow">✦ YOUR AI VOICE COMPANION</span>

            <h2>
              Every voice has a <span>story.</span>
            </h2>

            <p>
              Capture conversations. Transform speech into meaningful text.
            </p>
          </div>

          <div className="welcome-decoration">✧</div>
        </section>

        <div className="studio-grid">
          <section className="recording-card">
            <div className="card-heading">
              <div>
                <span className="eyebrow">RECORDING STUDIO</span>
                <h2>Voice capture</h2>
              </div>

              <span className="live-badge">
                <span className="status-dot"></span>
                {isRecording ? 'RECORDING' : 'STANDBY'}
              </span>
            </div>

            <div className={`mic-area ${isRecording ? 'recording' : ''}`}>
              <div className="mic-ring ring-one"></div>
              <div className="mic-ring ring-two"></div>

              <div className="mic-button">
                <span>🎙</span>
              </div>
            </div>

            <h3 className="record-title">
              {isRecording
                ? 'Listening to your voice...'
                : 'Ready when you are'}
            </h3>

            <p className="record-description">
              {isRecording
                ? 'Your recording session is active.'
                : 'Press the button below to start capturing your voice.'}
            </p>

            <div
              className="waveform"
              aria-label="Audio waveform visualization"
            >
              {Array.from({ length: 37 }, (_, i) => (
                <span
                  key={i}
                  style={{
                    height: `${12 + ((i * 17 + 13) % 34)}px`,
                    animationDelay: `${i * 0.045}s`,
                  }}
                />
              ))}
            </div>

            <div className="record-controls">
              <button
                className={`record-button ${isRecording ? 'stop-button' : ''}`}
                type="button"
                aria-pressed={isRecording}
                onClick={isRecording ? stopRecording : startRecording}
              >
                {isRecording ? 'Stop Recording' : 'Start Voice Capture'}
              </button>
            </div>

            {errorMessage && (
              <p style={{ color: '#ff6b81', textAlign: 'center' }}>
                {errorMessage}
              </p>
            )}

            <div className="record-footer">
              <span>◉ Microphone input</span>
              <span>✦ AI-powered transcription</span>
            </div>
          </section>

          <section className="transcript-card">
            <div className="card-heading">
              <div>
                <span className="eyebrow">LIVE CONVERSION</span>
                <h2>
                  {selectedSession ? 'Saved Transcript' : 'Transcript'}
                </h2>
              </div>

              <span className="document-icon">▤</span>
            </div>

            <div className="transcript-meta">
              <span>
                {selectedSession ? 'SAVED SESSION' : 'SESSION #001'}
              </span>

              <span className="language-badge">ENGLISH</span>
            </div>

            <div className="transcript-content">
              {!selectedSession && (
                <TranscriptTimeline segments={segments} />
              )}

              <p
                style={{
                  color: '#e4e5f0',
                  lineHeight: 1.8,
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                }}
              >
                {displayedTranscript ||
                  (isRecording
                    ? 'Listening... Start speaking.'
                    : 'Your recognized speech will appear here.')}
              </p>
            </div>

            <button
              type="button"
              onClick={downloadTranscript}
              disabled={!displayedTranscript.trim()}
              style={{
                marginTop: '16px',
                padding: '11px 20px',
                borderRadius: '9px',
                border: 'none',
                background: 'linear-gradient(135deg, #8055e8, #5945bd)',
                color: '#ffffff',
                fontWeight: 600,
                cursor: displayedTranscript.trim() ? 'pointer' : 'not-allowed',
                opacity: displayedTranscript.trim() ? 1 : 0.5,
              }}
            >
              ↓ Download Transcript
            </button>

            <div className="transcript-bottom">
              <span>✦ Powered by SDK-9 Voice Engine</span>
              <span>
                {selectedSession
                  ? selectedSession.date
                  : 'Live speech recognition'}
              </span>
            </div>
          </section>
        </div>

        {/* Recording History */}
        <section className="recording-card" style={{ marginTop: '24px' }}>
          <div className="card-heading">
            <div>
              <span className="eyebrow">YOUR PREVIOUS SESSIONS</span>
              <h2>Recording History</h2>
            </div>

            <span className="document-icon">
              {recordingHistory.length}
            </span>
          </div>

          {recordingHistory.length === 0 ? (
            <p className="record-description">
              No previous recordings yet. Complete a recording to see it here.
            </p>
          ) : (
            <div style={{ display: 'grid', gap: '12px' }}>
              {recordingHistory.map((session, index) => (
                <div
                  key={session.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedSessionId(session.id)}
                    style={{
                      flex: 1,
                      minWidth: 0,
                      textAlign: 'left',
                      padding: '16px',
                      borderRadius: '12px',
                      border: '1px solid rgba(160, 140, 255, 0.2)',
                      background:
                        selectedSessionId === session.id
                          ? 'rgba(130, 100, 255, 0.18)'
                          : 'rgba(255, 255, 255, 0.03)',
                      color: '#e4e5f0',
                      cursor: 'pointer',
                    }}
                  >
                    <strong>
                      Recording #{recordingHistory.length - index}
                    </strong>

                    <p
                      style={{
                        fontSize: '12px',
                        color: '#a9a8c4',
                        margin: '6px 0',
                      }}
                    >
                      {session.date}
                    </p>

                    <p
                      style={{
                        fontSize: '14px',
                        margin: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {session.transcript}
                    </p>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      if (
                        window.confirm(
                          'Are you sure you want to delete this recording?'
                        )
                      ) {
                        deleteSession(session.id);
                      }
                    }}
                    style={{
                      padding: '12px',
                      borderRadius: '8px',
                      border: '1px solid rgba(255, 100, 120, 0.4)',
                      background: 'rgba(255, 80, 100, 0.12)',
                      color: '#ff8295',
                      cursor: 'pointer',
                    }}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}

          {selectedSessionId && (
            <button
              type="button"
              onClick={() => setSelectedSessionId(null)}
              style={{
                marginTop: '16px',
                padding: '9px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
              }}
            >
              Back to Live Transcript
            </button>
          )}
        </section>

        <section className="feature-strip">
          <div className="feature">
            <span className="feature-icon purple">◉</span>
            <div>
              <strong>Voice intelligence</strong>
              <small>Speech capture interface</small>
            </div>
          </div>

          <div className="feature">
            <span className="feature-icon cyan">≋</span>
            <div>
              <strong>Audio visualization</strong>
              <small>Animated waveform</small>
            </div>
          </div>

          <div className="feature">
            <span className="feature-icon pink">✧</span>
            <div>
              <strong>Smart transcription</strong>
              <small>Speech-to-text workspace</small>
            </div>
          </div>
        </section>

        <footer className="footer">
          <span>ECHO AI · POWERED BY SDK-9</span>
          <span>BUILT FOR BETTER COMMUNICATION ✦</span>
        </footer>
      </section>
    </main>
  );
};