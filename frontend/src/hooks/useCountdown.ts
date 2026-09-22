import { useEffect, useState } from "react";

// Ticks `initialSeconds` down to 0 once a second — used to keep a submit
// button disabled for exactly as long as a backend rate-limit lockout
// lasts (see `retryAfterSeconds` in src/lib/errors.ts, surfaced on
// /auth/login, /auth/login-2fa and /auth/verify-2fa 429/403 responses).
export function useCountdown(initialSeconds: number | undefined): number | undefined {
  const [remaining, setRemaining] = useState(initialSeconds);

  useEffect(() => {
    setRemaining(initialSeconds);
    if (!initialSeconds || initialSeconds <= 0) return;
    const interval = setInterval(() => {
      setRemaining((prev) => {
        if (prev === undefined || prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [initialSeconds]);

  return remaining;
}
