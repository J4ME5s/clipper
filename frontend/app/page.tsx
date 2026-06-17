'use client';

import { useState, useEffect } from 'react';
import ClipResult from './components/ClipResult';
import UploadZone from './components/UploadZone';

export type Clip = {
  file: string;
  reason: string;
};

type ProcessResult = {
  job_id: string;
  clips: Clip[];
};

type Stage = 'idle' | 'downloading' | 'transcribing' | 'analyzing' | 'cutting' | 'done' | 'error';
type InputMode = 'file' | 'url';

const STAGE_LABELS: Record<Stage, string> = {
  idle: '',
  downloading: 'downloading video...',
  transcribing: 'transcribing audio...',
  analyzing: 'analyzing moments...',
  cutting: 'cutting clips...',
  done: 'done',
  error: 'something went wrong',
};

export default function Home() {
  const [stage, setStage] = useState<Stage>('idle');
  const [result, setResult] = useState<ProcessResult | null>(null);
  const [error, setError] = useState<string>('');
  const [light, setLight] = useState(false);

  const [inputMode, setInputMode] = useState<InputMode>('url');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');

  const [useTimestamps, setUseTimestamps] = useState(false);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');

  // Whether to burn captions into the output clips
  const [captions, setCaptions] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('light', light);
  }, [light]);

  const hasInput = inputMode === 'file' ? !!selectedFile : url.trim().length > 0;
  const isProcessing = ['downloading', 'transcribing', 'analyzing', 'cutting'].includes(stage);

  async function handleProcess() {
    if (!hasInput) return;

    setError('');
    setResult(null);
    setStage('downloading');

    try {
      const stageTimer = simulateStages(setStage, inputMode);
      const form = new FormData();

      if (inputMode === 'file' && selectedFile) {
        form.append('file', selectedFile);
      } else {
        form.append('url', url.trim());
        if (useTimestamps && startTime) form.append('start_time', startTime);
        if (useTimestamps && endTime) form.append('end_time', endTime);
      }

      // Send captions flag as string — FastAPI reads it as Form field
      form.append('captions', captions ? 'true' : 'false');

      const res = await fetch('http://127.0.0.1:8000/process', {
        method: 'POST',
        body: form,
      });

      clearTimeout(stageTimer.transcribe);
      clearTimeout(stageTimer.analyze);
      clearTimeout(stageTimer.cut);

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || 'Server error');
      }

      const data: ProcessResult = await res.json();
      setResult(data);
      setStage('done');
    } catch (err: unknown) {
      setStage('error');
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }

  function handleReset() {
    setStage('idle');
    setResult(null);
    setError('');
    setSelectedFile(null);
    setUrl('');
    setStartTime('');
    setEndTime('');
    setUseTimestamps(false);
    setCaptions(false);
  }

  return (
    <main style={{ position: 'relative', zIndex: 1, minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '80px 24px 120px', gap: '64px' }}>

      {/* Theme toggle */}
      <button
        onClick={() => setLight(!light)}
        className="mono"
        style={{ position: 'fixed', top: '20px', right: '24px', background: 'transparent', color: 'var(--muted)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 12px', cursor: 'pointer', zIndex: 10 }}
      >
        {light ? 'dark' : 'light'}
      </button>

      {/* Header */}
      <header style={{ textAlign: 'center' }}>
        <p className="mono" style={{ color: 'var(--accent)', marginBottom: '12px' }}>clip.ai — v0.1</p>
        <h1 style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 'clamp(2rem, 5vw, 3.5rem)', fontWeight: 500, letterSpacing: '-0.02em', lineHeight: 1.1, color: 'var(--text)' }}>
          stream clipper
        </h1>
        <p style={{ marginTop: '16px', color: 'var(--muted)', fontSize: '0.95rem', maxWidth: '420px' }}>
          drop a stream vod. get the best moments, cut and ready to post.
        </p>
      </header>

      {/* Input section */}
      <section style={{ width: '100%', maxWidth: '560px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

        {/* File / URL switcher */}
        <div style={{ display: 'flex', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden', width: 'fit-content' }}>
          {(['url', 'file'] as InputMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => !isProcessing && setInputMode(mode)}
              className="mono"
              style={{
                padding: '7px 18px',
                background: inputMode === mode ? 'var(--accent)' : 'transparent',
                color: inputMode === mode ? '#0a0a0a' : 'var(--muted)',
                border: 'none',
                cursor: isProcessing ? 'not-allowed' : 'pointer',
                fontWeight: inputMode === mode ? 500 : 400,
              }}
            >
              {mode}
            </button>
          ))}
        </div>

        {/* URL input + options */}
        {inputMode === 'url' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <input
              type="text"
              placeholder="paste a youtube or twitch url..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isProcessing}
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '14px 16px', color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem', outline: 'none', width: '100%' }}
            />

            {/* Timestamp range toggle */}
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
              <input
                type="checkbox"
                checked={useTimestamps}
                onChange={(e) => setUseTimestamps(e.target.checked)}
                disabled={isProcessing}
                style={{ accentColor: 'var(--accent)', width: '14px', height: '14px' }}
              />
              <span className="mono" style={{ color: 'var(--muted)' }}>clip a specific time range</span>
            </label>

            {useTimestamps && (
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <input type="text" placeholder="start (e.g. 6:00)" value={startTime} onChange={(e) => setStartTime(e.target.value)} disabled={isProcessing} style={{ ...tsInputStyle, flex: 1 }} />
                <span className="mono" style={{ color: 'var(--muted)' }}>to</span>
                <input type="text" placeholder="end (e.g. 36:00)" value={endTime} onChange={(e) => setEndTime(e.target.value)} disabled={isProcessing} style={{ ...tsInputStyle, flex: 1 }} />
              </div>
            )}
          </div>
        )}

        {/* File upload */}
        {inputMode === 'file' && (
          <UploadZone selectedFile={selectedFile} onFileSelect={setSelectedFile} disabled={isProcessing} />
        )}

        {/* Captions toggle — shown for both modes */}
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={captions}
            onChange={(e) => setCaptions(e.target.checked)}
            disabled={isProcessing}
            style={{ accentColor: 'var(--accent)', width: '14px', height: '14px' }}
          />
          <span className="mono" style={{ color: 'var(--muted)' }}>burn in captions</span>
        </label>

        {/* Status */}
        {stage !== 'idle' && (
          <div className="mono" style={{ color: stage === 'error' ? 'var(--danger)' : 'var(--accent)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isProcessing && <Spinner />}
            {STAGE_LABELS[stage]}
          </div>
        )}

        {error && <p className="mono" style={{ color: 'var(--danger)', fontSize: '0.7rem' }}>{error}</p>}

        {/* Action buttons */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '12px' }}>
          {stage !== 'done' && (
            <button
              onClick={handleProcess}
              disabled={!hasInput || isProcessing}
              style={{
                background: hasInput && !isProcessing ? 'var(--accent)' : 'var(--border)',
                color: hasInput && !isProcessing ? '#0a0a0a' : 'var(--muted)',
                border: 'none', borderRadius: 'var(--radius)', padding: '12px 28px',
                fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem', fontWeight: 500,
                cursor: hasInput && !isProcessing ? 'pointer' : 'not-allowed',
                transition: 'background 0.15s', letterSpacing: '0.04em',
              }}
            >
              {isProcessing ? 'processing...' : 'process video'}
            </button>
          )}

          {(stage === 'done' || stage === 'error') && (
            <button
              onClick={handleReset}
              style={{ background: 'transparent', color: 'var(--muted)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '12px 28px', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.8rem', cursor: 'pointer', letterSpacing: '0.04em' }}
            >
              start over
            </button>
          )}
        </div>
      </section>

      {/* Results */}
      {result && (
        <section style={{ width: '100%', maxWidth: '800px' }}>
          <p className="mono" style={{ color: 'var(--muted)', marginBottom: '24px' }}>
            {result.clips.length} clips found — job {result.job_id.slice(0, 8)}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {result.clips.map((clip, i) => (
              <ClipResult key={clip.file} clip={clip} index={i + 1} jobId={result.job_id} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

const tsInputStyle: React.CSSProperties = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '10px 12px',
  color: 'var(--text)',
  fontFamily: 'IBM Plex Mono, monospace',
  fontSize: '0.8rem',
  outline: 'none',
};

function simulateStages(setStage: (s: Stage) => void, mode: InputMode) {
  const downloadDelay = mode === 'url' ? 8000 : 1000;
  const transcribe = setTimeout(() => setStage('transcribing'), downloadDelay);
  const analyze = setTimeout(() => setStage('analyzing'), downloadDelay + 15000);
  const cut = setTimeout(() => setStage('cutting'), downloadDelay + 40000);
  return { transcribe, analyze, cut };
}

function Spinner() {
  return (
    <span style={{ display: 'inline-block', width: '10px', height: '10px', border: '1.5px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} />
  );
}