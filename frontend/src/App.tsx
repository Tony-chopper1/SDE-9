import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { AppShell } from './components/AppShell';
import { VoiceControls } from './components/VoiceControls';
import { TranscriptTimeline } from './components/TranscriptTimeline';
import { SessionHistory } from './components/SessionHistory';
import { ContextSourcePanel } from './components/ContextSourcePanel';
import { WorkflowProgressCard } from './components/WorkflowProgressCard';
import { ApprovalDialog } from './components/ApprovalDialog';
import { ErrorBoundary } from './components/ErrorBoundary';
import {
  TranscriptSegment,
  TypedVoicebotClient,
  EventStreamStatus,
  EventEnvelope,
} from './api_client';
import { RecordingSession } from './types/speech';
import {
  ActionPlan,
  WorkflowPlanPayload,
  WorkflowStepUpdatePayload,
  ApprovalRequest,
} from './types/workflow';
import { useVoiceRecorder } from './hooks/useVoiceRecorder';
import { EngineStatusData } from './components/EngineStatusPanel';

const STORAGE_KEY = 'academia-voice-history';
const LEGACY_STORAGE_KEY = 'echo-recording-history';

export const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'studio' | 'transcripts' | 'history'>('studio');
  const [recordingHistory, setRecordingHistory] = useState<RecordingSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  // Screen Context toggle state - strictly defaults to OFF for privacy
  const [isScreenContextEnabled, setIsScreenContextEnabled] = useState(false);

  // Engine status reported by backend health check and voice runtime
  const [engineStatus, setEngineStatus] = useState<EngineStatusData>({
    engineName: null,
    latencyMs: null,
    speechApiStatus: 'unknown',
    speechApiLabel: 'Not reported',
    backendStatus: 'unknown',
  });

  // State for backend-reported mock mode (from health check only)
  const [isMockMode, setIsMockMode] = useState<boolean>(false);

  // Week 3 D15-16: Live Backend Session & Event Stream Connection
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const [, setBackendSessionStatus] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<EventStreamStatus>('Disconnected');
  const streamCleanupRef = useRef<(() => void) | null>(null);

  // Week 3 D18: Agentic Workflow Action Plan State
  const [activePlan, setActivePlan] = useState<ActionPlan | null>(null);
  const [isDemoPlan, setIsDemoPlan] = useState<boolean>(false);

  // Week 3 D19: Human-in-the-Loop Approval & Rejection UI State
  const [activeApprovalRequest, setActiveApprovalRequest] = useState<ApprovalRequest | null>(null);
  const [isApprovalDialogOpen, setIsApprovalDialogOpen] = useState<boolean>(false);
  const [, setDecidedRequestIds] = useState<Set<string>>(new Set());
  const decidedRequestIdsRef = useRef<Set<string>>(new Set());
  const activePlanRef = useRef<ActionPlan | null>(null);

  useEffect(() => {
    activePlanRef.current = activePlan;
  }, [activePlan]);

  // Query backend health to retrieve actual engine name, measured round-trip latency, and mock mode
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
          setIsMockMode(res.data?.mock_mode === true);
          setEngineStatus((prev) => ({
            ...prev,
            engineName: res.data?.service || null,
            latencyMs: latency,
            backendStatus: isHealthy ? 'online' : 'unknown',
          }));
        }
      } catch {
        if (isMounted) {
          setIsMockMode(false);
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
      revision: 1,
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
        revision: 1,
      };
      setSegments((prev) => [...prev, newSegment]);
    },
    [persistHistory, recordingHistory, segments.length]
  );

  const {
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
  } = useVoiceRecorder({
    onSessionComplete: handleSessionComplete,
  });

  // Selected session lookup
  const selectedSession = useMemo(() => {
    return recordingHistory.find((s) => s.id === selectedSessionId) || null;
  }, [recordingHistory, selectedSessionId]);

  // Week 3: Connect to backend session and SSE event stream when voice capture starts
  const initBackendSessionAndStream = useCallback(async () => {
    setStreamStatus('Connecting');
    try {
      const client = new TypedVoicebotClient();
      const res = await client.createSession();
      if (res.success && res.data?.session_id) {
        const sid = res.data.session_id;
        setBackendSessionId(sid);
        setBackendSessionStatus(res.data.status || 'created');

        if (streamCleanupRef.current) {
          streamCleanupRef.current();
        }

        const cleanup = client.subscribeToSessionEvents(sid, {
          onStatusChange: (status) => {
            setStreamStatus(status);
          },
          onEvent: (event: EventEnvelope) => {
            if (event.event_type === 'session.status' && event.payload?.status) {
              setBackendSessionStatus(String(event.payload.status));
            } else if (event.event_type === 'workflow.plan' && event.payload) {
              // Handle incoming workflow plan
              const payload = event.payload as unknown as WorkflowPlanPayload;
              const planData = payload.plan || (payload as unknown as ActionPlan);
              if (planData && planData.goal) {
                setActivePlan(planData);
                setIsDemoPlan(false);
              }
            } else if (event.event_type === 'workflow.step' && event.payload) {
              // Handle step-level update
              const update = event.payload as unknown as WorkflowStepUpdatePayload;
              setActivePlan((prev) => {
                if (!prev) return prev;
                // Verify the event's plan_id matches the active plan before updating
                if (update.plan_id && update.plan_id !== prev.plan_id) {
                  return prev;
                }

                const updatedSteps = prev.steps.map((step) => {
                  const isMatch =
                    (update.step_id && step.id === update.step_id) ||
                    (update.id && step.id === update.id) ||
                    (typeof update.step_number === 'number' && step.step_number === update.step_number);
                  if (!isMatch) return step;
                  return {
                    ...step,
                    status: update.status || step.status,
                    result: update.result !== undefined ? update.result : step.result,
                    error: update.error !== undefined ? update.error : step.error,
                    tool_name: update.tool_name || step.tool_name,
                  };
                });

                // Safe plan status transitions: verify pending/running steps
                const hasRunning = updatedSteps.some((s) => s.status === 'running');
                const hasPending = updatedSteps.some((s) => s.status === 'pending');
                const hasFailed = updatedSteps.some((s) => s.status === 'failed');
                const hasRejected = updatedSteps.some((s) => s.status === 'rejected');
                const hasCancelled = updatedSteps.some((s) => s.status === 'cancelled');
                const allCompleted =
                  updatedSteps.length > 0 && updatedSteps.every((s) => s.status === 'completed');

                let nextPlanStatus = prev.status;
                if (hasFailed) {
                  nextPlanStatus = 'FAILED';
                } else if (hasRejected) {
                  nextPlanStatus = 'REJECTED';
                } else if (hasCancelled && !hasRunning && !hasPending) {
                  nextPlanStatus = 'CANCELLED';
                } else if (allCompleted && !hasRunning && !hasPending) {
                  nextPlanStatus = 'COMPLETED';
                } else if (hasRunning) {
                  nextPlanStatus = 'EXECUTING';
                }

                return {
                  ...prev,
                  steps: updatedSteps,
                  status: nextPlanStatus,
                  current_step_index:
                    typeof update.step_number === 'number'
                      ? Math.max(0, update.step_number - 1)
                      : prev.current_step_index,
                };
              });
            } else if (event.event_type === 'approval.request' && event.payload) {
              // Week 3 D19: Handle incoming human approval request
              const req = event.payload as unknown as Partial<ApprovalRequest>;
              const reqId = req.request_id || `req-${Date.now()}`;
              if (!decidedRequestIdsRef.current.has(reqId)) {
                const targetPlan = activePlanRef.current;
                const validatedRequest: ApprovalRequest = {
                  request_id: reqId,
                  plan_id: req.plan_id || targetPlan?.plan_id || 'unknown-plan',
                  session_id: req.session_id || sid,
                  safety_level: req.safety_level || (targetPlan?.overall_safety_level === 'D' ? 'D' : 'C'),
                  status: 'PENDING',
                  created_at: req.created_at || Date.now() / 1000,
                  action: req.action || req.description,
                  description: req.description,
                  tool_name: req.tool_name,
                  step_number: req.step_number,
                  step_id: req.step_id,
                  parameters: req.parameters,
                  risks: req.risks,
                  risk_assessment: req.risk_assessment,
                };

                setActiveApprovalRequest(validatedRequest);
                setIsApprovalDialogOpen(true);

                // Transition plan status to AWAITING_APPROVAL
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  if (validatedRequest.plan_id && validatedRequest.plan_id !== prev.plan_id) {
                    return prev;
                  }
                  if (
                    prev.status === 'COMPLETED' ||
                    prev.status === 'FAILED' ||
                    prev.status === 'REJECTED'
                  ) {
                    return prev;
                  }
                  return {
                    ...prev,
                    status: 'AWAITING_APPROVAL',
                  };
                });
              }
            }
          },
          onError: () => {
            setStreamStatus('Error');
          },
        });
        streamCleanupRef.current = cleanup;
      } else {
        setStreamStatus('Error');
      }
    } catch {
      // Gracefully handle session creation failure without breaking voice recording
      setStreamStatus('Error');
    }
  }, []);

  // Demo workflow fixture for testing in mock mode (strictly badged as simulated)
  const handleTriggerDemoPlan = useCallback(() => {
    const demoPlan: ActionPlan = {
      plan_id: `plan-demo-${Date.now()}`,
      session_id: backendSessionId || 'session-simulated-demo',
      goal: 'Scan workspace files, extract error metrics, and calculate summary stats',
      current_step_index: 0,
      overall_safety_level: 'B',
      requires_approval: false,
      status: 'EXECUTING',
      created_at: Date.now() / 1000,
      steps: [
        {
          id: 'step-demo-1',
          step_number: 1,
          description: 'Search workspace files for error diagnostic logs',
          tool_name: 'file.search',
          safety_level: 'A',
          status: 'completed',
          result: { files: ['logs/diagnostic_report.json'] },
          retry_count: 0,
        },
        {
          id: 'step-demo-2',
          step_number: 2,
          description: 'Read file content and extract latency samples',
          tool_name: 'file.read',
          safety_level: 'B',
          status: 'running',
          retry_count: 0,
        },
        {
          id: 'step-demo-3',
          step_number: 3,
          description: 'Evaluate statistical median and error rate',
          tool_name: 'calculator.eval',
          safety_level: 'A',
          status: 'pending',
          retry_count: 0,
        },
      ],
    };
    setActivePlan(demoPlan);
    setIsDemoPlan(true);
  }, [backendSessionId]);

  // Week 3 D19: Human-in-the-Loop Approval Decision Handlers
  const handleApproveAction = useCallback((requestId: string, reason?: string) => {
    // Prevent duplicate decisions
    if (decidedRequestIdsRef.current.has(requestId)) {
      return;
    }
    decidedRequestIdsRef.current.add(requestId);
    setDecidedRequestIds(new Set(decidedRequestIdsRef.current));

    setActiveApprovalRequest((prev) => {
      if (!prev || prev.request_id !== requestId) return prev;
      return {
        ...prev,
        status: 'APPROVED',
        decided_at: Date.now() / 1000,
        decided_by: 'operator',
        reason,
      };
    });

    // Update active plan status to APPROVED
    // Note: Do not claim live backend execution when unsupported by backend
    setActivePlan((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        status: 'APPROVED',
        approved_at: Date.now() / 1000,
      };
    });

    setIsApprovalDialogOpen(false);
  }, []);

  const handleRejectAction = useCallback((requestId: string, reason?: string) => {
    // Prevent duplicate decisions
    if (decidedRequestIdsRef.current.has(requestId)) {
      return;
    }
    decidedRequestIdsRef.current.add(requestId);
    setDecidedRequestIds(new Set(decidedRequestIdsRef.current));

    setActiveApprovalRequest((prev) => {
      if (!prev || prev.request_id !== requestId) return prev;
      return {
        ...prev,
        status: 'REJECTED',
        decided_at: Date.now() / 1000,
        decided_by: 'operator',
        reason: reason || 'Rejected by operator',
      };
    });

    // Non-negotiable safety rule: Rejection must NEVER trigger execution!
    // Safely mark active plan and all pending/running steps as rejected
    setActivePlan((prev) => {
      if (!prev) return prev;
      const updatedSteps = prev.steps.map((step) => {
        if (step.status === 'pending' || step.status === 'running') {
          return { ...step, status: 'rejected' as const };
        }
        return step;
      });
      return {
        ...prev,
        status: 'REJECTED',
        rejected_at: Date.now() / 1000,
        rejection_reason: reason || 'Rejected by operator',
        steps: updatedSteps,
      };
    });

    setIsApprovalDialogOpen(false);
  }, []);

  const closeBackendSessionAndStream = useCallback(() => {
    if (streamCleanupRef.current) {
      streamCleanupRef.current();
      streamCleanupRef.current = null;
    }
    setStreamStatus('Disconnected');
  }, []);

  // Cleanup stream on component unmount
  useEffect(() => {
    return () => {
      if (streamCleanupRef.current) {
        streamCleanupRef.current();
        streamCleanupRef.current = null;
      }
    };
  }, []);

  // Handle start/stop toggle
  const handleToggleRecording = useCallback(() => {
    if (isRecording) {
      closeBackendSessionAndStream();
      stopRecording();
    } else {
      setSelectedSessionId(null);
      void initBackendSessionAndStream();
      startRecording();
    }
  }, [isRecording, closeBackendSessionAndStream, initBackendSessionAndStream, startRecording, stopRecording]);

  const handleStopRecording = useCallback(() => {
    closeBackendSessionAndStream();
    stopRecording();
  }, [closeBackendSessionAndStream, stopRecording]);

  // Accessible Keyboard Shortcuts (Alt+P, Alt+R, Alt+C)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore shortcuts if the user is typing in an input or textarea
      const active = document.activeElement;
      if (
        active &&
        (active.tagName === 'INPUT' ||
          active.tagName === 'TEXTAREA' ||
          (active as HTMLElement).isContentEditable)
      ) {
        return;
      }

      if (e.altKey && (e.key === 'p' || e.key === 'P')) {
        e.preventDefault();
        if (recordingState === 'recording') {
          pauseRecording();
        } else if (recordingState === 'paused') {
          resumeRecording();
        }
      } else if (e.altKey && (e.key === 'r' || e.key === 'R')) {
        e.preventDefault();
        if (recordingState === 'idle') {
          setSelectedSessionId(null);
          void initBackendSessionAndStream();
          startRecording();
        } else {
          closeBackendSessionAndStream();
          stopRecording();
        }
      } else if (e.altKey && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault();
        setIsScreenContextEnabled((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [recordingState, pauseRecording, resumeRecording, startRecording, stopRecording, initBackendSessionAndStream, closeBackendSessionAndStream]);

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

  // Dynamic segments to render in timeline (with in-place interim updates and revisions)
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
          revision: 1,
        },
      ];
    }

    if (isRecording && (currentSegment?.text || liveTranscript)) {
      const interimText = currentSegment?.text || liveTranscript;
      const interimSegment: TranscriptSegment = {
        id: currentSegment?.id || 'interim-live',
        text: interimText,
        confidence: currentSegment?.confidence ?? 0.88,
        start_time: currentSegment?.start_time ?? (segments.length * 2),
        end_time: currentSegment?.end_time ?? (segments.length * 2 + 3),
        is_final: currentSegment ? currentSegment.is_final : false,
        revision: currentSegment?.revision ?? liveRevision,
      };
      return [...segments, interimSegment];
    }

    return segments;
  }, [selectedSession, isRecording, currentSegment, liveTranscript, segments, liveRevision]);

  // Derive Speech API status from live voice recorder runtime state
  const computedEngineStatus = useMemo<EngineStatusData>(() => {
    let speechApiStatus: 'online' | 'offline' | 'unknown' = 'unknown';
    let speechApiLabel = 'Not reported';

    if (recordingState === 'recording') {
      speechApiStatus = 'online';
      speechApiLabel = 'Active';
    } else if (recordingState === 'paused') {
      speechApiStatus = 'online';
      speechApiLabel = 'Paused';
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
  }, [engineStatus, recordingState, errorMessage]);

  const isServiceOnline = computedEngineStatus.backendStatus !== 'offline';

  return (
    <AppShell
      activeTab={activeTab}
      onTabChange={setActiveTab}
      serviceOnline={isServiceOnline}
      engineStatus={computedEngineStatus}
      streamStatus={streamStatus}
    >
      {/* Visible Mock Mode Banner */}
      {isMockMode && (
        <div
          className="mock-mode-banner"
          role="status"
          aria-label="Mock Mode Active"
        >
          <span className="mock-badge" aria-hidden="true">MOCK MODE</span>
          <span className="mock-text">
            <strong>Running in Mock Mode:</strong> Backend services are operating in simulated test mode.
          </span>
        </div>
      )}

      {/* Enterprise Hero Banner */}
      <section className="hero-banner" aria-label="Overview Banner">
        <div className="hero-content">
          <span className="hero-eyebrow">ENTERPRISE VOICE INTELLIGENCE</span>
          <h1 className="hero-heading">
            AI Voice <span className="hero-highlight">Co-Pilot</span>
          </h1>
          <p className="hero-description">
            Context-aware voice assistance, real-time speech transcription, and multimodal workspace reasoning.
          </p>
        </div>
      </section>

      {/* Main Studio Two-Column Grid */}
      <div className="saas-grid-container">
        {/* Left Column: Voice Capture Controls */}
        <div className="grid-column-left">
          <VoiceControls
            isRecording={isRecording}
            recordingState={recordingState}
            isPaused={isPaused}
            isOffline={!isServiceOnline}
            onToggleRecording={handleToggleRecording}
            onPause={pauseRecording}
            onResume={resumeRecording}
            onStop={handleStopRecording}
            errorMessage={errorMessage}
            onDismissError={() => setErrorMessage('')}
            micPermission={micPermission}
            streamStatus={streamStatus}
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
                  aria-label="Export TXT - download current transcript as text file"
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
                {backendSessionId
                  ? `Backend Session: ${backendSessionId.slice(0, 8)}...`
                  : (selectedSession ? `Recorded: ${selectedSession.date}` : 'Real-time speech stream')}
              </span>
              <span className="panel-meta-text">
                Language: <strong className="lang-code">en-US</strong>
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* Week 3 D18 & D19: Agentic Workflow & Human Approval Section */}
      <div className="workflow-section-wrapper">
        {/* Pending Approval Banner when modal is dismissed without decision */}
        {activeApprovalRequest && activeApprovalRequest.status === 'PENDING' && !isApprovalDialogOpen && (
          <div className="pending-approval-card-banner" role="region" aria-label="Pending authorization request">
            <div className="pending-approval-info">
              <span aria-hidden="true">⚠️</span>
              <span>
                Authorization pending for Level {activeApprovalRequest.safety_level} action:{' '}
                <strong>{activeApprovalRequest.action || activeApprovalRequest.tool_name || 'Workflow Step'}</strong>
              </span>
            </div>
            <button
              type="button"
              className="pending-approval-review-btn"
              onClick={() => setIsApprovalDialogOpen(true)}
              aria-label="Review pending approval request"
            >
              Review Authorization
            </button>
          </div>
        )}

        <WorkflowProgressCard
          plan={activePlan}
          isMockMode={isMockMode}
          isDemoPlan={isDemoPlan}
          onTriggerDemoPlan={handleTriggerDemoPlan}
          onClearPlan={() => {
            setActivePlan(null);
            setIsDemoPlan(false);
          }}
        />
      </div>

      {/* Multimodal Context & Source Panel Section */}
      <div className="context-section-wrapper">
        <ContextSourcePanel
          sessionId={backendSessionId || selectedSessionId || undefined}
          isScreenContextEnabled={isScreenContextEnabled}
          onToggleScreenContext={setIsScreenContextEnabled}
          isOffline={!isServiceOnline}
        />
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

      {/* Week 3 D19: Human-in-the-Loop Approval Modal Dialog */}
      <ApprovalDialog
        isOpen={isApprovalDialogOpen}
        request={activeApprovalRequest}
        associatedPlan={activePlan}
        isDemo={isDemoPlan}
        onApprove={handleApproveAction}
        onReject={handleRejectAction}
        onClose={() => setIsApprovalDialogOpen(false)}
      />
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
