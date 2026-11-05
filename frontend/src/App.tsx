import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { AppShell } from './components/AppShell';
import { VoiceControls } from './components/VoiceControls';
import { TranscriptTimeline } from './components/TranscriptTimeline';
import { SessionHistory } from './components/SessionHistory';
import { ErrorBoundary } from './components/ErrorBoundary';
import { TranscriptSegment, TypedVoicebotClient } from './api_client';
import { RecordingSession } from './types/speech';
import { useVoiceRecorder } from './hooks/useVoiceRecorder';
import { EngineStatusData } from './components/EngineStatusPanel';

const STORAGE_KEY = 'academia-voice-history';
const LEGACY_STORAGE_KEY = 'echo-recording-history';

export const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'studio' | 'transcripts' | 'history'>('studio');
  const [recordingHistory, setRecordingHistory] = useState<RecordingSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  // Engine status reported by backend health check and voice runtime
  const [engineStatus, setEngineStatus] = useState<EngineStatusData>({
    engineName: null,
    latencyMs: null,
    speechApiStatus: 'unknown',
    speechApiLabel: 'Not reported',
    backendStatus: 'unknown',
  });

  // Query backend health to retrieve actual engine name and measured round-trip latency
  useEffect(() => {
    let isMounted = true;
    const client = new TypedVoicebotClient();

    const fetchEngineHealth = async () => {
      try {
        const startTime = performance.now();
        const res = await client.checkHealth();
        const latency = Math.round(performance.now() - startTime);

        if (isMounted) {
          const isHealthy = res.data?.status === 'healthy';
          setEngineStatus((prev) => ({
            ...prev,
            engineName: res.data?.service || null,
            latencyMs: latency,
            backendStatus: isHealthy ? 'online' : 'unknown',
          }));
        }
      } catch {
        if (isMounted) {
          setEngineStatus((prev) => ({
            ...prev,
            engineName: null,
            latencyMs: null,
            backendStatus: 'offline',
          }));
        }
      }
    };

    fetchEngineHealth();
    return () => {
      isMounted = false;
    };
  }, []);

  // Active timeline segments for visualization
  const [segments, setSegments] = useState<TranscriptSegment[]>([
    {
      id: 'demo-welcome',
      text: 'AI Voice Co-Pilot initialized and ready for voice input.',
      confidence: 0.99,
      start_time: 0,
      end_time: 2,
      is_final: true,
    },
  ]);

  // Load history from browser storage (supporting legacy key as fallback)
  useEffect(() => {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        return;
      }
      const saved = window.localStorage.getItem(STORAGE_KEY) ||
                    window.localStorage.getItem(LEGACY_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as RecordingSession[];
        setRecordingHistory(parsed);
      }
    } catch {
      // Storage unavailable or unparseable; ignore gracefully
    }
  }, []);

  // Save updated history
  const persistHistory = useCallback((updated: RecordingSession[]) => {
    setRecordingHistory(updated);
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      }
    } catch {
      // Fallback if quota exceeded
    }
  }, []);

  // Handle completed voice session
  const handleSessionComplete = useCallback(
    (completedTranscript: string) => {
      const clean = completedTranscript.trim();
      if (!clean) return;

      const newSession: RecordingSession = {
        id: `session-${Date.now()}`,
        date: new Date().toLocaleString(),
        transcript: clean,
      };

      const updated = [newSession, ...recordingHistory];
      persistHistory(updated);
      setSelectedSessionId(newSession.id);

      // Append to timeline segments
      const newSegment: TranscriptSegment = {
        id: `seg-${Date.now()}`,
        text: clean,
        confidence: 0.95,
        start_time: Math.max(0, segments.length * 2),
        end_time: Math.max(0, segments.length * 2) + Math.ceil(clean.length / 15),
        is_final: true,
      };
      setSegments((prev) => [...prev, newSegment]);
    },
    [persistHistory, recordingHistory, segments.length]
  );

  const {
    isRecording,
    liveTranscript,
    errorMessage,
    setErrorMessage,
    startRecording,
    stopRecording,
  } = useVoiceRecorder({
    onSessionComplete: handleSessionComplete,
  });

  // Selected session lookup
  const selectedSession = useMemo(() => {
    return recordingHistory.find((s) => s.id === selectedSessionId) || null;
  }, [recordingHistory, selectedSessionId]);

  // Handle start/stop toggle
  const handleToggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      setSelectedSessionId(null);
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  // Download transcript as file
  const handleDownloadTranscript = useCallback((session?: RecordingSession) => {
    let textToDownload = '';
    if (session) {
      textToDownload = session.transcript;
    } else if (selectedSession) {
      textToDownload = selectedSession.transcript;
    } else if (liveTranscript.trim()) {
      textToDownload = liveTranscript;
    } else if (segments.length > 0) {
      textToDownload = segments.map((s) => s.text).join('\n');
    }

    const clean = textToDownload.trim();
    if (!clean) {
      setErrorMessage('There is no transcript available to download.');
      return;
    }

    const blob = new Blob([clean], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `academia-transcript-${Date.now()}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [selectedSession, liveTranscript, segments, setErrorMessage]);

  // Delete session
  const handleDeleteSession = useCallback(
    (sessionId: string) => {
      const updated = recordingHistory.filter((s) => s.id !== sessionId);
      persistHistory(updated);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
      }
    },
    [persistHistory, recordingHistory, selectedSessionId]
  );

  // Dynamic segments to render in timeline
  const activeTimelineSegments = useMemo(() => {
    if (selectedSession) {
      return [
        {
          id: selectedSession.id,
          text: selectedSession.transcript,
          confidence: 1.0,
          start_time: 0,
          end_time: Math.max(2, Math.ceil(selectedSession.transcript.length / 15)),
          is_final: true,
        },
      ];
    }

    if (isRecording && liveTranscript) {
      const interimSegment: TranscriptSegment = {
        id: 'interim-live',
        text: liveTranscript,
        confidence: 0.88,
        start_time: segments.length * 2,
        end_time: segments.length * 2 + 3,
        is_final: false,
      };
      return [...segments, interimSegment];
    }

    return segments;
  }, [selectedSession, isRecording, liveTranscript, segments]);

  // Derive Speech API status from live voice recorder runtime state
  const computedEngineStatus = useMemo<EngineStatusData>(() => {
    let speechApiStatus: 'online' | 'offline' | 'unknown' = 'unknown';
    let speechApiLabel = 'Not reported';

    if (isRecording) {
      speechApiStatus = 'online';
      speechApiLabel = 'Active';
    } else if (
      errorMessage &&
      (errorMessage.toLowerCase().includes('microphone') ||
       errorMessage.toLowerCase().includes('speech recognition'))
    ) {
      speechApiStatus = 'offline';
      speechApiLabel = 'Offline';
    }

    return {
      ...engineStatus,
      speechApiStatus,
      speechApiLabel,
    };
  }, [engineStatus, isRecording, errorMessage]);

  const isServiceOnline = computedEngineStatus.backendStatus !== 'offline';

  return (
    <AppShell
      activeTab={activeTab}
      onTabChange={setActiveTab}
      serviceOnline={isServiceOnline}
      engineStatus={computedEngineStatus}
    >
      {/* Enterprise Hero Banner */}
      <section className="hero-banner" aria-label="Overview Banner">
        <div className="hero-content">
          <span className="hero-eyebrow">ENTERPRISE VOICE INTELLIGENCE</span>
          <h1 className="hero-heading">
            AI Voice <span className="hero-highlight">Co-Pilot</span>
          </h1>
          <p className="hero-description">
            Context-aware voice assistance and real-time speech transcription designed for
            seamless workspace productivity.
          </p>
        </div>
      </section>

      {/* Main Studio Two-Column Grid */}
      <div className="saas-grid-container">
        {/* Left Column: Voice Capture Controls */}
        <div className="grid-column-left">
          <VoiceControls
            isRecording={isRecording}
            onToggleRecording={handleToggleRecording}
            errorMessage={errorMessage}
            onDismissError={() => setErrorMessage('')}
          />
        </div>

        {/* Right Column: Live Transcript & Timeline */}
        <div className="grid-column-right">
          <section className="transcript-panel-card" aria-label="Transcript Viewer">
            <div className="card-header">
              <div>
                <span className="section-eyebrow">LIVE CONVERSION</span>
                <h2 className="card-title">
                  {selectedSession ? 'Saved Session Transcript' : 'Transcript Timeline'}
                </h2>
              </div>

              <div className="card-header-actions">
                <button
                  type="button"
                  className="download-action-btn"
                  onClick={() => handleDownloadTranscript()}
                  disabled={!selectedSession && !liveTranscript.trim() && segments.length === 0}
                  aria-label="Download current transcript as text file"
                  title="Download transcript"
                >
                  ↓ Export TXT
                </button>
              </div>
            </div>

            <div className="transcript-body">
              {/* Virtualized Timeline Component */}
              <TranscriptTimeline
                segments={activeTimelineSegments}
                viewportHeight={340}
              />
            </div>

            <div className="panel-footer-info">
              <span className="panel-meta-text">
                {selectedSession ? `Recorded: ${selectedSession.date}` : 'Real-time speech stream'}
              </span>
              <span className="panel-meta-text">
                Language: <strong className="lang-code">en-US</strong>
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* Session History Section */}
      <div className="history-section-wrapper">
        <SessionHistory
          history={recordingHistory}
          selectedSessionId={selectedSessionId}
          onSelectSession={setSelectedSessionId}
          onDeleteSession={handleDeleteSession}
          onDownloadTranscript={handleDownloadTranscript}
        />
      </div>
    </AppShell>
  );
};

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <AppContent />
    </ErrorBoundary>
  );
};
