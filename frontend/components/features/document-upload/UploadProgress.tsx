export function UploadProgress({ value = 0 }: { value?: number }) {
  return (
    <div aria-label="Upload progress" className="h-2 rounded-full bg-white/10">
      <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(value, 100)}%` }} />
    </div>
  );
}
