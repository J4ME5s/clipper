'use client';

import { useRef, useState } from 'react';

type Props = {
  selectedFile: File | null;
  onFileSelect: (file: File) => void;
  disabled: boolean;
};

export default function UploadZone({ selectedFile, onFileSelect, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('video/')) onFileSelect(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onFileSelect(file);
  }

  // Format bytes into human-readable size
  function formatSize(bytes: number) {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      style={{
        border: `1px solid ${dragging ? 'var(--accent)' : selectedFile ? 'var(--border)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: '40px 32px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        background: dragging ? 'rgba(200, 241, 53, 0.04)' : 'var(--surface)',
        transition: 'border-color 0.15s, background 0.15s',
        textAlign: 'center',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        onChange={handleChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />

      {selectedFile ? (
        /* Show selected file info */
        <div>
          <p className="mono" style={{ color: 'var(--accent)' }}>
            {selectedFile.name}
          </p>
          <p className="mono" style={{ color: 'var(--muted)', marginTop: '6px' }}>
            {formatSize(selectedFile.size)}
          </p>
        </div>
      ) : (
        /* Default empty state */
        <div>
          <p style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
            drag a video here
          </p>
          <p className="mono" style={{ color: 'var(--muted)', marginTop: '8px' }}>
            or click to browse
          </p>
        </div>
      )}
    </div>
  );
}