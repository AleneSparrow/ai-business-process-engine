import { Suspense, lazy, type ReactNode } from "react";
import { BrandLink } from "./BrandLockup";

const OrbitScene = lazy(() => import("./OrbitScene").then((mod) => ({ default: mod.OrbitScene })));

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="ev-page relative min-h-screen overflow-hidden flex items-center justify-center px-6">
      <div className="absolute inset-0 pointer-events-none opacity-80">
        <Suspense fallback={null}>
          <OrbitScene variant="ambient" />
        </Suspense>
      </div>
      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <BrandLink to="/" />
        </div>
        {children}
      </div>
    </div>
  );
}
