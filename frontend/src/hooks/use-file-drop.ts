import { useState, type DragEvent } from 'react';

const ACCEPTED_EXTS = ['.pdf', '.docx', '.txt', '.md', '.fasta', '.fa', '.faa', '.zip'];

export function isAcceptedUploadFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTS.some((ext) => name.endsWith(ext));
}

export function useFileDrop(
  onFiles: (files: File[]) => void,
  onRejected?: (files: File[]) => void,
) {
  const [isDragOver, setIsDragOver] = useState(false);

  const hasFiles = (e: DragEvent) =>
    Array.from(e.dataTransfer.types || []).includes('Files');

  const handlers = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setIsDragOver(true);
    },
    onDragOver: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      setIsDragOver(true);
    },
    onDragLeave: (e: DragEvent) => {
      if (e.currentTarget === e.target) setIsDragOver(false);
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      setIsDragOver(false);
      const dropped = Array.from(e.dataTransfer.files || []);
      const accepted = dropped.filter(isAcceptedUploadFile);
      const rejected = dropped.filter((f) => !isAcceptedUploadFile(f));
      if (rejected.length > 0) onRejected?.(rejected);
      if (accepted.length > 0) onFiles(accepted);
    },
  };

  return { isDragOver, dropHandlers: handlers };
}
