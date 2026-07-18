"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, StatusResponse } from "@/lib/api";

const STAGES = [
  { key: "compiling", label: "Compiling", icon: "⚙️" },
  { key: "planning", label: "Planning Scenes", icon: "📋" },
  { key: "generating", label: "Generating Assets", icon: "🎨" },
  { key: "rendering", label: "Rendering Video", icon: "🎬" },
  { key: "completed", label: "Ready!", icon: "✅" },
];

export default function StatusPage() {
  const params = useSearchParams();
  const projectId = params.get("id");
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) return;

    const poll = async () => {
      try {
        const data = await api.getStatus(projectId);
        setStatus(data);

        if (data.status !== "completed" && data.status !== "failed") {
          setTimeout(poll, 3000);
        }
      } catch (err: any) {
        setError(err.message);
      }
    };

    poll();
  }, [projectId]);

  if (!projectId) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p style={{ color: "var(--text-secondary)" }}>No project ID provided</p>
      </main>
    );
  }

  const currentStageIndex = STAGES.findIndex((s) => s.key === status?.stage);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-lg">
        <h1 className="text-2xl font-bold text-center mb-8"
          style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
          {status?.status === "completed"
            ? "Your Reel is ready"
            : "Creating your cinematic Reel"}
        </h1>

        {error && (
          <div className="rounded-lg px-4 py-3 text-sm mb-6"
            style={{ background: "rgba(255,71,87,0.1)", color: "var(--error)" }}>
            {error}
          </div>
        )}

        {/* Progress stages */}
        <div className="rounded-2xl p-6"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>

          <div className="space-y-4">
            {STAGES.map((stage, i) => {
              const isActive = stage.key === status?.stage;
              const isDone = i < currentStageIndex;
              const isPending = i > currentStageIndex;

              return (
                <div key={stage.key} className="flex items-center gap-4">
                  {/* Status indicator */}
                  <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg shrink-0"
                    style={{
                      background: isDone ? "rgba(46,213,115,0.15)"
                        : isActive ? "rgba(108,92,231,0.15)"
                          : "var(--bg-secondary)",
                      border: `1px solid ${isDone ? "var(--success)"
                        : isActive ? "var(--accent)"
                          : "var(--border)"}`,
                    }}>
                    {isDone ? "✓" : isActive ? stage.icon : "○"}
                  </div>

                  {/* Label */}
                  <div className="flex-1">
                    <p className="text-sm font-medium"
                      style={{
                        color: isDone ? "var(--success)"
                          : isActive ? "var(--text-primary)"
                            : "var(--text-secondary)"
                      }}>
                      {stage.label}
                    </p>
                    {isActive && (
                      <div className="mt-2 h-1.5 rounded-full overflow-hidden"
                        style={{ background: "var(--bg-secondary)" }}>
                        <div className="h-full rounded-full transition-all duration-500"
                          style={{
                            background: "var(--accent)",
                            width: `${(status?.progress || 0) * 100}%`,
                          }} />
                      </div>
                    )}
                  </div>

                  {/* Scene count for generating stage */}
                  {isActive && status && status.scenes_total > 0 && (
                    <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                      {status.scenes_completed}/{status.scenes_total}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Download button when ready */}
          {status?.status === "completed" && (
            <div className="mt-8">
              <button
                onClick={() => window.open(status.download_url || "#", "_blank")}
                className="w-full rounded-xl py-4 text-base font-semibold transition-all"
                style={{
                  background: "var(--success)",
                  color: "#fff",
                }}
              >
                Download Reel
              </button>
              <p className="text-center text-xs mt-3" style={{ color: "var(--text-secondary)" }}>
                Ready for YouTube Shorts or Instagram Reels
              </p>
            </div>
          )}

          {status?.status === "failed" && (
            <div className="mt-6 rounded-lg px-4 py-3"
              style={{ background: "rgba(255,71,87,0.1)", border: "1px solid var(--error)" }}>
              <p className="text-sm" style={{ color: "var(--error)" }}>
                Generation failed. Please try again.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
