import { useState, useRef, useEffect, useCallback } from 'react';
import {
  ISpeechRecognition,
  ISpeechRecognitionConstructor,
  SpeechRecognitionEvent,
  SpeechRecognitionErrorEvent,
} from '../types/speech';

interface WindowWithSpeech extends Window {
  SpeechRecognition?: ISpeechRecognitionConstructor;
  webkitSpeechRecognition?: ISpeechRecognitionConstructor;
}

interface UseVoiceRecorderOptions {
  onSessionComplete?: (transcript: string) => void;
}

export function useVoiceRecorder(options: UseVoiceRecorderOptions = {}) {
  const { onSessionComplete } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState('');
  const [errorMessage, setErrorMessage] = useState('');

  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const finalTranscriptRef = useRef('');
  const currentFullTranscriptRef = useRef('');
  const shouldSaveOnEndRef = useRef(false);

  // Stop active media stream tracks
  const cleanupStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    try {
      setErrorMessage('');
      setLiveTranscript('');
      finalTranscriptRef.current = '';
      currentFullTranscriptRef.current = '';
      shouldSaveOnEndRef.current = false;

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Microphone access is not supported in this browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

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

      setIsRecording(true);

      // Check SpeechRecognition
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
        let interimText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const item = event.results[i];
          const segmentText = item[0]?.transcript ?? '';
          if (item.isFinal) {
            finalTranscriptRef.current += segmentText + ' ';
          } else {
            interimText += segmentText;
          }
        }
        const combined = (finalTranscriptRef.current + interimText).trim();
        currentFullTranscriptRef.current = combined;
        setLiveTranscript(combined);
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        const errMsg = event.error === 'not-allowed'
          ? 'Microphone permission was denied. Please allow microphone access in your browser settings.'
          : `Speech recognition error: ${event.error}`;
        setErrorMessage(errMsg);
      };

      recognition.onend = () => {
        if (shouldSaveOnEndRef.current && onSessionComplete) {
          onSessionComplete(currentFullTranscriptRef.current);
          shouldSaveOnEndRef.current = false;
        }
        recognitionRef.current = null;
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: unknown) {
      cleanupStream();
      setIsRecording(false);
      const message = err instanceof Error
        ? (err.name === 'NotAllowedError'
            ? 'Microphone permission was denied. Please allow microphone access to record.'
            : err.message)
        : 'Unable to access microphone. Please verify permissions.';
      setErrorMessage(message);
    }
  }, [cleanupStream, onSessionComplete]);

  const stopRecording = useCallback(() => {
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

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    } else {
      cleanupStream();
    }

    setIsRecording(false);
  }, [cleanupStream, onSessionComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
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
    liveTranscript,
    errorMessage,
    setErrorMessage,
    startRecording,
    stopRecording,
  };
}
