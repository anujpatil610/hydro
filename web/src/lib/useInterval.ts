import { useEffect, useRef } from "react";

export function useInterval(fn: () => void, ms: number) {
  const saved = useRef(fn);
  useEffect(() => {
    saved.current = fn;
  }, [fn]);
  useEffect(() => {
    const tick = () => saved.current();
    tick();
    const id = setInterval(tick, ms);
    return () => clearInterval(id);
  }, [ms]);
}
