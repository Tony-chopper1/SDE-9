import { useState, useRef, useEffect, useCallback } from 'react';
import {
  ISpeechRecognition,
  ISpeechRecognitionConstructor,
  MicPermissionState,
  SpeechRecognitionEvent,
  SpeechRecognitionErrorEvent,
  RecordingState,
  LiveTranscriptSegment,
} from '../types/speech';

interface WindowWithSpeech extends Window {
  SpeechRecognition?: ISpeechRecognitionConstructor;
  webkitSpeechRecognition?: ISpeechRecognitionConstructor;
}

interface UseVoiceRecorderOptions {
  onSessionComplete?: (transcript: string) => void;
  onSegmentUpdate?: (segment: LiveTranscriptSegment) => void;
}

export function useVoiceRecorder(options: UseVoiceRecorderOptions = {}) {
  const { onSessionComplete, onSegmentUpdate } = options;

  const [recordingState, setRecordingState] = useState<RecordingState>('idle');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [liveRevision, setLiveRevision] = useState(0);
  const [currentSegment, setCurrentSegment] = useState<LiveTranscriptSegment | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [micPermission, setMicPermission] = useState<MicPermissionState>(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      return 'unsupported';
    }
    return 'prompt';
  });

  const isRecording = recordingState === 'recording' || recordingState === 'paused';
  const isPaused = recordingState === 'paused';

  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const finalTranscriptRef = useRef('');
  const currentFullTranscriptRef = useRef('');
  const shouldSaveOnEndRef = useRef(false);
  const isPausedRef = useRef(false);

  // Segment and revision tracking
  const segmentRevisionRef = useRef(0);
  const currentSegmentIdRef = useRef('');
  const sessionStartTimeRef = useRef(0);
  const currentSegmentStartTimeRef = useRef(0);

  // Sync with browser Permissions API when available
  useEffect(() => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setMicPermission('unsupported');
      return;
    }

    let isMounted = true;
    let permStatus: PermissionStatus | null = null;

    const checkPermissionApi = async () => {
      try {
        if (navigator.permissions && typeof navigator.permissions.query === 'function') {
          const status = await navigator.permissions.query({ name: 'microphone' as PermissionName });
          if (!isMounted) return;
          permStatus = status;

          const mapState = (state: PermissionState): MicPermissionState => {
            if (state === 'granted') return 'granted';
            if (state === 'denied') return 'denied';
            return 'prompt';
          };

          setMicPermission(mapState(status.state));

          status.onchange = () => {
            if (!isMounted) return;
            setMicPermission(mapState(status.state));
          };
        }
      } catch {
        // Permissions API query for microphone not supported or rejected;
        // fallback gracefully to prompt
        if (isMounted) {
          setMicPermission((prev) => (prev === 'unsupported' ? 'unsupported' : 'prompt'));
        }
      }
    };

    checkPermissionApi();

    return () => {
      isMounted = false;
      if (permStatus) {
        permStatus.onchange = null;
      }
    };
  }, []);

  // Stop active media stream tracks
  const cleanupStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  // Helper to instantiate and start SpeechRecognition safely
  const startSpeechRecognition = useCallback(() => {
    const win = window as unknown as WindowWithSpeech;
    const SpeechRecognitionClass = win.SpeechRecognition || win.webkitSpeechRecognition;

    if (!SpeechRecognitionClass) {
      setErrorMessage('Speech recognition is not supported in this browser. Audio recording is still active.');
      return;
    }

    const recognition = new SpeechRecognitionClass();
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      if (isPausedRef.current) {
        return;
      }

      let interimText = '';
      let latestConfidence = 0.95;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const item = event.results[i];
        const segmentText = item[0]?.transcript ?? '';
        const conf = item[0]?.confidence ?? 0.95;
        if (conf > 0) {
          latestConfidence = conf;
        }

        if (item.isFinal) {
          finalTranscriptRef.current += segmentText + ' ';
          segmentRevisionRef.current += 1;
          const finalSeg: LiveTranscriptSegment = {
            id: currentSegmentIdRef.current || `seg-${Date.now()}`,
            text: segmentText.trim(),
            confidence: latestConfidence,
            start_time: currentSegmentStartTimeRef.current,
            end_time: sessionStartTimeRef.current ? (Date.now() - sessionStartTimeRef.current) / 1000 : 0,
            is_final: true,
            revision: segmentRevisionRef.current,
          };
          setCurrentSegment(finalSeg);
          if (onSegmentUpdate) {
            onSegmentUpdate(finalSeg);
          }

          // Reset segment ID and revision for the next utterance
          currentSegmentIdRef.current = `seg-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
          segmentRevisionRef.current = 0;
          currentSegmentStartTimeRef.current = sessionStartTimeRef.current
            ? (Date.now() - sessionStartTimeRef.current) / 1000
            : 0;
        } else {
          interimText += segmentText;
        }
      }

      const combined = (finalTranscriptRef.current + interimText).trim();
      currentFullTranscriptRef.current = combined;
      setLiveTranscript(combined);

      if (interimText.trim()) {
        segmentRevisionRef.current += 1;
        setLiveRevision(segmentRevisionRef.current);
        const interimSeg: LiveTranscriptSegment = {
          id: currentSegmentIdRef.current || `seg-${Date.now()}`,
          text: interimText.trim(),
          confidence: latestConfidence,
          start_time: currentSegmentStartTimeRef.current,
          end_time: sessionStartTimeRef.current ? (Date.now() - sessionStartTimeRef.current) / 1000 : 0,
          is_final: false,
          revision: segmentRevisionRef.current,
        };
        setCurrentSegment(interimSeg);
        if (onSegmentUpdate) {
          onSegmentUpdate(interimSeg);
        }
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (isPausedRef.current) {
        return;
      }
      const errMsg = event.error === 'not-allowed'
        ? 'Microphone permission was denied. Please allow microphone access in your browser settings.'
        : `Speech recognition error: ${event.error}`;
      if (event.error === 'not-allowed') {
        setMicPermission('denied');
      }
      setErrorMessage(errMsg);
    };

    recognition.onend = () => {
      if (isPausedRef.current) {
        // Paused state: do NOT trigger onSessionComplete or wipe data
        recognitionRef.current = null;
        return;
      }
      if (shouldSaveOnEndRef.current && onSessionComplete) {
        onSessionComplete(currentFullTranscriptRef.current);
        shouldSaveOnEndRef.current = false;
      }
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      // Ignore start error if already running
    }
  }, [onSegmentUpdate, onSessionComplete]);

  const startRecording = useCallback(async () => {
    try {
      setErrorMessage('');
      setLiveTranscript('');
      setLiveRevision(0);
      setCurrentSegment(null);
      finalTranscriptRef.current = '';
      currentFullTranscriptRef.current = '';
      shouldSaveOnEndRef.current = false;
      isPausedRef.current = false;
      segmentRevisionRef.current = 0;
      sessionStartTimeRef.current = Date.now();
      currentSegmentStartTimeRef.current = 0;
      currentSegmentIdRef.current = `seg-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;

      if (!navigator.mediaDevices?.getUserMedia) {
        setMicPermission('unsupported');
        throw new Error('Microphone access is not supported in this browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      setMicPermission('granted');

      // Initialize MediaRecorder
      if (typeof MediaRecorder !== 'undefined') {
        const recorder = new MediaRecorder(stream);
        audioChunksRef.current = [];

        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data && event.data.size > 0) {
            audioChunksRef.current.push(event.data);
          }
        };

        recorder.onstop = () => {
          cleanupStream();
        };

        mediaRecorderRef.current = recorder;
        recorder.start();
      }

      setRecordingState('recording');
      startSpeechRecognition();
    } catch (err: unknown) {
      cleanupStream();
      setRecordingState('idle');
      const isDenied = err instanceof Error && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError');
      if (isDenied) {
        setMicPermission('denied');
      }
      const message = err instanceof Error
        ? (isDenied
            ? 'Microphone permission was denied. Please allow microphone access to record.'
            : err.message)
        : 'Unable to access microphone. Please verify permissions.';
      setErrorMessage(message);
    }
  }, [cleanupStream, startSpeechRecognition]);

  const pauseRecording = useCallback(() => {
    if (recordingState !== 'recording') return;

    isPausedRef.current = true;
    setRecordingState('paused');

    // Pause MediaRecorder where supported
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      if (typeof mediaRecorderRef.current.pause === 'function') {
        mediaRecorderRef.current.pause();
      }
    }

    // Stop SpeechRecognition safely while preserving session transcript
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore stop error
      }
    }
  }, [recordingState]);

  const resumeRecording = useCallback(() => {
    if (recordingState !== 'paused') return;

    isPausedRef.current = false;
    setRecordingState('recording');

    // Resume MediaRecorder where supported
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'paused') {
      if (typeof mediaRecorderRef.current.resume === 'function') {
        mediaRecorderRef.current.resume();
      }
    }

    // Restart SpeechRecognition
    startSpeechRecognition();
  }, [recordingState, startSpeechRecognition]);

  const stopRecording = useCallback(() => {
    isPausedRef.current = false;
    const recognition = recognitionRef.current;
    if (recognition) {
      shouldSaveOnEndRef.current = true;
      try {
        recognition.stop();
      } catch {
        shouldSaveOnEndRef.current = false;
        if (onSessionComplete) {
          onSessionComplete(currentFullTranscriptRef.current);
        }
      }
    } else if (onSessionComplete) {
      onSessionComplete(currentFullTranscriptRef.current);
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    } else {
      cleanupStream();
    }

    setRecordingState('idle');
    setCurrentSegment(null);
    setLiveRevision(0);
  }, [cleanupStream, onSessionComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isPausedRef.current = false;
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore cleanup abort errors
        }
      }
      cleanupStream();
    };
  }, [cleanupStream]);

  return {
    isRecording,
    isPaused,
    recordingState,
    liveTranscript,
    liveRevision,
    currentSegment,
    errorMessage,
    setErrorMessage,
    micPermission,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
  };
}
