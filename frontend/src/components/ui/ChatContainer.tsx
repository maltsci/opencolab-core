import type { ReactNode } from 'react';

interface ChatContainerProps {
  children: ReactNode;
  composer: ReactNode;
  topBar?: ReactNode;
}

export default function ChatContainer({ children, composer, topBar }: ChatContainerProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {topBar ? <div style={{ flexShrink: 0 }}>{topBar}</div> : null}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {children}
      </div>
      <div style={{ flexShrink: 0, paddingTop: 12 }}>
        {composer}
      </div>
    </div>
  );
}
