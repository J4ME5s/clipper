'use client';

import { useState } from 'react';
import { Clip } from '../page';

type Props = {
  clip: Clip;
  index: number;
  jobId: string;
};

export default function ClipResult({ clip, index, jobId }: Props) {
  const [expanded, setExpanded] = useState(false);

  // URL pointing to the backend download endpoint
  const clipUrl = `http://127.0.0.1:8000/clips/${jobId}/${clip.file}`;

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        background: 'var(--surface)',
        overflow: 'hidden',
      }}
    >
      {/* Clip header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Clip number badge */}
          <span
            className="mono"
            style={{
              background: 'var(--accent)',
              color: '#0a0a0a',
              padding: '2px 8px',
              borderRadius: 'var(--radius)',
              fontWeight: 500,
            }}
          >
            {String(index).padStart(2, '0')}
          </span>

          {/* Reason label from LLM */}
          <span style={{ color: 'var(--muted)', fontSize: '0.875rem' }}>
            {clip.reason}
          </span>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mono"
            style={{
              background: 'transparent',
              color: 'var(--muted)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: '6px 12px',
              cursor: 'pointer',
              fontSize: '0.7rem',
            }}
          >
            {expanded ? 'hide' : 'preview'}
          </button>

          <a
            href={clipUrl}
            download={clip.file}
            className="mono"
            style={{
              background: 'var(--accent)',
              color: '#0a0a0a',
              border: 'none',
              borderRadius: 'var(--radius)',
              padding: '6px 12px',
              cursor: 'pointer',
              fontSize: '0.7rem',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            download
          </a>
        </div>
      </div>

      {/* Expandable video preview */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)' }}>
          <video
            src={clipUrl}
            controls
            style={{ width: '100%', display: 'block', maxHeight: '400px', background: '#000' }}
          />
        </div>
      )}
    </div>
  );
}