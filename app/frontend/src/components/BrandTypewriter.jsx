import { useEffect, useRef } from "react";

const WORD = "naw";

export default function BrandTypewriter() {
  const elRef = useRef(null);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let len = WORD.length;
    let deleting = true;
    let timer;

    const tick = () => {
      if (deleting) {
        if (len > 1) {
          len -= 1;
          el.textContent = WORD.slice(0, len);
          timer = setTimeout(tick, 90);
        } else {
          deleting = false;
          timer = setTimeout(tick, 450);
        }
      } else if (len < WORD.length) {
        len += 1;
        el.textContent = WORD.slice(0, len);
        timer = setTimeout(tick, 105);
      } else {
        deleting = true;
        timer = setTimeout(tick, 2800);
      }
    };

    el.textContent = WORD;
    timer = setTimeout(tick, 2800);
    return () => clearTimeout(timer);
  }, []);

  return (
    <span className="brand-name">
      <span ref={elRef}>{WORD}</span>
      <span className="brand-cursor" aria-hidden="true" />
    </span>
  );
}
