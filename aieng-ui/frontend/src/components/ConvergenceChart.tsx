import { useMemo } from "react";

import {
  buildConvergenceSeries,
  formatIterationObjective,
  verdictLabel,
  type ConvergencePoint,
  type OptimizationConvergence,
} from "../app/optimizationConvergence";

type ConvergenceChartProps = {
  convergence: OptimizationConvergence;
  /** Accessible title for the chart. */
  title?: string;
};

const WIDTH = 400;
const HEIGHT = 180;
const MARGIN = { top: 10, right: 12, bottom: 32, left: 44 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;

export function ConvergenceChart({ convergence, title = "Optimization convergence" }: ConvergenceChartProps) {
  const series = useMemo(() => buildConvergenceSeries(convergence), [convergence]);

  const { xScale, yScale, ticks } = useMemo(() => {
    const objectives = series.map((p) => p.objective).filter((v): v is number => v !== null);
    const minObj = objectives.length > 0 ? Math.min(...objectives) : 0;
    const maxObj = objectives.length > 0 ? Math.max(...objectives) : 1;
    const pad = objectives.length > 0 ? Math.max(0.02 * (maxObj - minObj), 0.001) : 0.5;
    const yMin = minObj - pad;
    const yMax = maxObj + pad;

    const xScale = (iteration: number) =>
      series.length <= 1 ? MARGIN.left + PLOT_WIDTH / 2 : MARGIN.left + ((iteration - 1) / (series.length - 1)) * PLOT_WIDTH;
    const yScale = (value: number) => MARGIN.top + PLOT_HEIGHT - ((value - yMin) / (yMax - yMin)) * PLOT_HEIGHT;

    const ticks = makeTicks(yMin, yMax);
    return { xScale, yScale, ticks };
  }, [series]);

  const pathD = useMemo(() => makePathD(series, xScale, yScale), [series, xScale, yScale]);

  const verdict = convergence.latest_verdict;

  return (
    <div className="convergence-chart" role="img" aria-label={title}>
      <div className="convergence-chart-head">
        <strong>{title}</strong>
        {verdict && (
          <span
            className={`convergence-verdict convergence-verdict-${verdict.converged ? "converged" : "running"}`}
            title={verdict.reason_codes.join(", ")}
          >
            {verdictLabel(verdict.verdict)}
          </span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        className="convergence-chart-svg"
        aria-hidden="true"
      >
        <desc>
          Convergence history across {series.length} iteration{series.length !== 1 ? "s" : ""}.
          Latest objective: {formatIterationObjective(series[series.length - 1]?.objective)}.
        </desc>

        {/* Y-axis grid + ticks */}
        {ticks.map((t) => {
          const y = yScale(t);
          return (
            <g key={t}>
              <line
                x1={MARGIN.left}
                y1={y}
                x2={MARGIN.left + PLOT_WIDTH}
                y2={y}
                className="convergence-grid-line"
              />
              <text x={MARGIN.left - 6} y={y + 3} className="convergence-axis-text convergence-axis-text-y">
                {formatTick(t)}
              </text>
            </g>
          );
        })}

        {/* Axes */}
        <line
          x1={MARGIN.left}
          y1={MARGIN.top + PLOT_HEIGHT}
          x2={MARGIN.left + PLOT_WIDTH}
          y2={MARGIN.top + PLOT_HEIGHT}
          className="convergence-axis-line"
        />
        <line
          x1={MARGIN.left}
          y1={MARGIN.top}
          x2={MARGIN.left}
          y2={MARGIN.top + PLOT_HEIGHT}
          className="convergence-axis-line"
        />

        {/* X-axis ticks */}
        {series.map((p) => (
          <text
            key={p.iteration}
            x={xScale(p.iteration)}
            y={MARGIN.top + PLOT_HEIGHT + 16}
            className="convergence-axis-text convergence-axis-text-x"
          >
            {p.iteration}
          </text>
        ))}

        {/* Feasible line */}
        {pathD && <path d={pathD} className="convergence-line" fill="none" />}

        {/* Points */}
        {series.map((p) => {
          const cx = xScale(p.iteration);
          const cy = p.objective !== null ? yScale(p.objective) : null;
          if (cy === null) {
            return (
              <text
                key={p.iteration}
                x={cx}
                y={MARGIN.top + PLOT_HEIGHT / 2}
                className="convergence-missing-point"
              >
                —
              </text>
            );
          }
          return (
            <circle
              key={p.iteration}
              cx={cx}
              cy={cy}
              r={4}
              className={`convergence-point ${p.feasible ? "convergence-point-feasible" : "convergence-point-infeasible"}`}
            />
          );
        })}
      </svg>

      <div className="convergence-chart-legend">
        <span className="convergence-legend-item">
          <span className="convergence-legend-dot convergence-legend-dot-feasible" />
          Feasible
        </span>
        <span className="convergence-legend-item">
          <span className="convergence-legend-dot convergence-legend-dot-infeasible" />
          Infeasible
        </span>
        {convergence.iterations.some((it) => it.safe_to_accept) && (
          <span className="convergence-legend-item convergence-legend-safe">✓ accept-ready reached</span>
        )}
      </div>
    </div>
  );
}

function makePathD(
  series: ConvergencePoint[],
  xScale: (i: number) => number,
  yScale: (v: number) => number,
): string | null {
  const segments: string[] = [];
  let current: string[] = [];

  for (const p of series) {
    if (p.objective === null) {
      if (current.length) {
        segments.push(current.join(" "));
        current = [];
      }
      continue;
    }
    const cmd = current.length === 0 ? "M" : "L";
    current.push(`${cmd}${xScale(p.iteration)},${yScale(p.objective)}`);
  }
  if (current.length) segments.push(current.join(" "));
  return segments.length ? segments.join(" ") : null;
}

function makeTicks(min: number, max: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [0];
  const target = 4;
  const rawStep = (max - min) / target;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const residual = rawStep / magnitude;
  const step = (residual <= 2 ? 2 : residual <= 5 ? 5 : 10) * magnitude;
  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 0.001; v += step) {
    ticks.push(Number(v.toFixed(6)));
  }
  return ticks.length > 1 ? ticks : [min, max];
}

function formatTick(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 10000 || (abs < 0.001 && abs > 0)) return value.toExponential(1);
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)));
}
