import React, { useState } from 'react';
import { TranscriptTimeline } from './components/TranscriptTimeline';
import { TranscriptSegment } from './api_client';

export const App: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
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

  return (
    <main
      role="main"
      style={{
        fontFamily: 'system-ui, sans-serif',
        maxWidth: '800px',
        margin: '40px auto',
        padding: '24px',
        border: '1px solid #ddd',
        borderRadius: '8px',
      }}
    >
      <header>
        <h1>SDK-9 — AI Voice Co-Pilot</h1>
        <p>Accessible, multimodal voice assistant layer.</p>
      </header>

      <div style={{ margin: '20px 0' }}>
        <button
          type="button"
          aria-pressed={isRecording}
          onClick={() => setIsRecording(!isRecording)}
          style={{
            padding: '12px 24px',
            fontSize: '16px',
            fontWeight: 'bold',
            backgroundColor: isRecording ? '#d9534f' : '#0275d8',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          {isRecording ? 'Stop Recording' : 'Start Voice Capture'}
        </button>
      </div>

      <TranscriptTimeline segments={segments} />
    </main>
  );
};
