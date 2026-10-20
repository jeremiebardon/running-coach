/**
 * Jack Daniels / Jimmy Gilbert "VDOT" model.
 *
 * VDOT = VO2 cost of running at velocity v / fraction of VO2max sustainable for t.
 * Unlike Riegel (a single power law), it encodes that the sustainable fraction of
 * VO2max decays with duration, which is why it tends to be more realistic for
 * extrapolating a 10k to a marathon.
 */

/** Oxygen cost (ml/kg/min) of running at v metres per minute */
const vo2AtVelocity = (v: number): number => -4.6 + 0.182258 * v + 0.000104 * v * v;

/** Fraction of VO2max sustainable for t minutes */
const sustainableFraction = (tMin: number): number =>
  0.8 + 0.1894393 * Math.exp(-0.012778 * tMin) + 0.2989558 * Math.exp(-0.1932605 * tMin);

export function vdotFromPerformance(distanceM: number, timeSec: number): number {
  const tMin = timeSec / 60;
  const v = distanceM / tMin;
  return vo2AtVelocity(v) / sustainableFraction(tMin);
}

/**
 * Inverse problem: the race time at `distanceM` that corresponds to `vdot`.
 * VDOT is strictly decreasing in time for a fixed distance, so bisection is
 * simple and robust (no derivative needed).
 */
export function predictTimeFromVdot(vdot: number, distanceM: number): number {
  let fast = (distanceM / 450) * 60; // 450 m/min ≈ 2:13/km, faster than any human
  let slow = (distanceM / 80) * 60; // 80 m/min ≈ 12:30/km
  for (let i = 0; i < 80; i++) {
    const mid = (fast + slow) / 2;
    if (vdotFromPerformance(distanceM, mid) > vdot) fast = mid;
    else slow = mid;
  }
  return (fast + slow) / 2;
}

/** Peter Riegel's power law T2 = T1 · (D2/D1)^k, k ≈ 1.06 */
export function riegel(timeSec: number, fromM: number, toM: number, exponent = 1.06): number {
  return timeSec * Math.pow(toM / fromM, exponent);
}
