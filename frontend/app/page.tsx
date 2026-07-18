"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

// Only languages the backend can actually voice today. Advertising Telugu/Hindi
// here while the pipeline is English-only means the UI accepts a request the
// backend immediately rejects (UnsupportedCapability) -- a worse experience than
// not offering it. Telugu + Hindi return at Phase 2 with IndicF5; add them here
// only when the backend registry reports them.
// TODO(phase-2): fetch from GET /api/v1/languages so this can't drift again.
const LANGUAGES = ["English"];

export default function Home() {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [language, setLanguage] = useState("English");
  const [duration, setDuration] = useState(60);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!idea.trim()) {
      setError("Please enter your video idea");
      return;
    }
    if (idea.trim().length < 10) {
      setError("Please describe your idea in more detail");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const project = await api.createVideo({ idea, language, duration });
      router.push(`/status?id=${project.id}`);
    } catch (err: any) {
      setError(err.message || "Something went wrong");
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      {/* Background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full opacity-20"
          style={{ background: "radial-gradient(circle, var(--accent-glow), transparent 70%)" }} />
      </div>

      <div className="relative z-10 w-full max-w-xl">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-6"
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            AI Video Compiler v1
          </div>

          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4"
            style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
            Turn your idea into a{" "}
            <span style={{ color: "var(--accent)" }}>cinematic Reel</span>
          </h1>

          <p style={{ color: "var(--text-secondary)" }} className="text-lg">
            One idea. Any language. 60 seconds. Ready to publish.
          </p>
        </div>

        {/* Creation Card */}
        <div className="rounded-2xl p-6 sm:p-8"
          style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>

          {/* Idea Input */}
          <div className="mb-6">
            <label className="block text-sm font-medium mb-2"
              style={{ color: "var(--text-secondary)" }}>
              What do you want to create?
            </label>
            <textarea
              value={idea}
              onChange={(e) => { setIdea(e.target.value); setError(""); }}
              placeholder="A village boy learns DevOps and gets a job at Google..."
              rows={4}
              className="w-full rounded-xl px-4 py-3 text-base resize-none focus:outline-none focus:ring-2 transition-all"
              style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
                focusRingColor: "var(--accent)",
              }}
              disabled={loading}
            />
          </div>

          {/* Language + Duration Row */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div>
              <label className="block text-sm font-medium mb-2"
                style={{ color: "var(--text-secondary)" }}>
                Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 appearance-none cursor-pointer"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
                disabled={loading}
              >
                {LANGUAGES.map((lang) => (
                  <option key={lang} value={lang}>{lang}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2"
                style={{ color: "var(--text-secondary)" }}>
                Duration
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[30, 60].map((d) => (
                  <button
                    key={d}
                    onClick={() => setDuration(d)}
                    className="rounded-xl px-4 py-3 text-sm font-medium transition-all"
                    style={{
                      background: duration === d ? "var(--accent)" : "var(--bg-secondary)",
                      border: `1px solid ${duration === d ? "var(--accent)" : "var(--border)"}`,
                      color: duration === d ? "#fff" : "var(--text-secondary)",
                    }}
                    disabled={loading}
                  >
                    {d}s
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg px-4 py-3 text-sm mb-4"
              style={{ background: "rgba(255,71,87,0.1)", color: "var(--error)" }}>
              {error}
            </div>
          )}

          {/* Generate Button */}
          <button
            onClick={handleGenerate}
            disabled={loading || !idea.trim()}
            className="w-full rounded-xl py-4 text-base font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: loading ? "var(--bg-secondary)" : "var(--accent)",
              color: "#fff",
              boxShadow: !loading ? "0 0 30px var(--accent-glow)" : "none",
            }}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Compiling your video...
              </span>
            ) : (
              "Generate Video"
            )}
          </button>
        </div>

        {/* Footer note */}
        <p className="text-center text-xs mt-6" style={{ color: "var(--text-secondary)" }}>
          No prompts. No timelines. No scene editing. Just your idea.
        </p>
      </div>
    </main>
  );
}
