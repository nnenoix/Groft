interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  strokeWidth?: number;
  fill?: boolean;
}

export function Sparkline({ values, width = 80, height = 22, strokeWidth = 1.5, fill = true }: SparklineProps) {
  if (!values || !values.length) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y] as [number, number];
  });
  const d = points.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(" ");
  const area = `M${points[0][0]},${height} ${d} L${points[points.length - 1][0]},${height} Z`;
  return (
    <svg width={width} height={height} className="spark block">
      {fill && <path d={area} fill="currentColor" opacity="0.12" />}
      <path d={d} stroke="currentColor" strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
