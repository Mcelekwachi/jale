import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorMessage } from "../components/ErrorMessage";
import { QuizFeedback } from "../components/QuizFeedback";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { defaultMetaLanguage } from "../lib/locale";
import type {
  MetaLanguage,
  StudyDirection,
  StudyItem,
  StudySession,
  UserProfile,
} from "../lib/types";
import {
  AnswerQueue,
  type AnswerResponse,
  type PendingAnswer,
} from "../study/answerQueue";
import { AudioButton } from "../study/AudioButton";
import { FlagSheet } from "../study/FlagSheet";

export function Study() {
  const { trackSlug = "", unitPosition = "" } = useParams();
  const [session, setSession] = useState<StudySession | null>(null);
  const [meta, setMeta] = useState<string>(defaultMetaLanguage());
  const [metaName, setMetaName] = useState("English");
  const [direction, setDirection] = useState<StudyDirection>("target_to_meta");
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [shownAt, setShownAt] = useState(Date.now());
  const [correct, setCorrect] = useState(0);
  const [summary, setSummary] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(false);
  const [queueError, setQueueError] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [slow, setSlow] = useState(false);
  const queue = useMemo(
    () =>
      new AnswerQueue((answers: PendingAnswer[]) =>
        apiFetch<AnswerResponse>("/v1/study/answers", {
          method: "POST",
          authenticated: true,
          body: JSON.stringify({ answers }),
        }),
      ),
    [],
  );
  useEffect(() => {
    let active = true;
    setSession(null);
    setIndex(0);
    setRevealed(false);
    void Promise.all([
      apiFetch<UserProfile>("/v1/me", { authenticated: true }),
      apiFetch<MetaLanguage[]>("/v1/languages/meta"),
    ])
      .then(async ([profile, languages]) => {
        const code = profile.preferences.meta_language ?? defaultMetaLanguage();
        const params = new URLSearchParams({ meta_language: code, direction });
        const next = await apiFetch<StudySession>(
          `/v1/tracks/${trackSlug}/units/${unitPosition}/items?${params}`,
          { authenticated: true, onSlowChange: (v) => active && setSlow(v) },
        );
        if (active) {
          setMeta(code);
          setMetaName(languages.find((l) => l.code === code)?.name ?? code);
          setSession(next);
          setShownAt(Date.now());
        }
      })
      .catch(
        (e: unknown) =>
          active &&
          setError(
            e instanceof Error
              ? e.message
              : "Could not load this study session",
          ),
      );
    return () => {
      active = false;
    };
  }, [direction, trackSlug, unitPosition]);
  const record = async (isCorrect: boolean) => {
    if (!session) return;
    setCorrect((value) => value + Number(isCorrect));
    try {
      await queue.add({
        content_id: session.items[index].id,
        correct: isCorrect,
        mode: session.mode,
        duration_ms: Date.now() - shownAt,
      });
      setQueueError(false);
    } catch {
      setQueueError(true);
    }
  };
  const advance = async (isCorrect?: boolean) => {
    if (!session || advancing) return;
    setAdvancing(true);
    if (isCorrect !== undefined) await record(isCorrect);
    if (index + 1 < session.items.length) {
      setIndex(index + 1);
      setRevealed(false);
      setShownAt(Date.now());
      setAdvancing(false);
    } else {
      try {
        const result = await queue.flush();
        setSummary(
          result ??
            queue.latestResponse ?? {
              results: [],
              current_streak: 0,
              today_xp: 0,
            },
        );
        setRetry(false);
      } catch {
        setRetry(true);
      }
    }
  };
  if (error)
    return (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    );
  if (!session)
    return (
      <Spinner
        label={slow ? "Waking the server…" : "Loading your study session"}
        fullScreen
      />
    );
  if (summary || retry)
    return (
      <main className="min-h-dvh bg-warm p-5">
        <section className="mx-auto max-w-md rounded-[2rem] bg-cream p-7 shadow-card">
          <h1 className="font-display text-4xl text-indigo-deep">
            Session complete
          </h1>
          <p className="mt-4">
            {session.items.length} items reviewed · {correct} correct
          </p>
          {summary && (
            <p className="mt-2">
              {summary.current_streak} day streak · {summary.today_xp} XP today
            </p>
          )}
          {retry && (
            <>
              <ErrorMessage message="Your answers are still safe in this session." />
              <button
                className="mt-4 min-h-11 rounded-xl bg-indigo-deep px-5 text-cream"
                onClick={() =>
                  void queue
                    .flush()
                    .then((r) => {
                      setSummary(r);
                      setRetry(false);
                    })
                    .catch(() => setRetry(true))
                }
              >
                Retry submission
              </button>
            </>
          )}
          <div className="mt-6 flex gap-3">
            <button
              className="min-h-11 rounded-xl border border-ochre px-4"
              onClick={() => {
                setSummary(null);
                setIndex(0);
                setCorrect(0);
                setAdvancing(false);
                setRevealed(false);
                setShownAt(Date.now());
              }}
            >
              Repeat unit
            </button>
            <Link
              className="inline-flex min-h-11 items-center rounded-xl bg-indigo-deep px-4 text-cream"
              to="/"
            >
              Return home
            </Link>
          </div>
        </section>
      </main>
    );
  const item = session.items[index];
  return (
    <main className="min-h-dvh bg-warm px-5 py-5 text-ink">
      <div className="mx-auto max-w-lg">
        <header className="flex items-center justify-between">
          <Link to="/" className="inline-flex min-h-11 items-center">
            ← Home
          </Link>
          <span>Item {index + 1} of {session.items.length}</span>
        </header>
        <p className="text-xs font-bold uppercase tracking-[.18em] text-terracotta">
          {session.track} · {session.unit_title}
        </p>
        {queueError && (
          <div className="my-3 rounded-xl bg-terracotta-soft p-3 text-sm">
            Answers are still safe in this session.{" "}
            <button
              className="min-h-11 font-bold underline"
              onClick={() =>
                void queue
                  .flush()
                  .then(() => setQueueError(false))
                  .catch(() => setQueueError(true))
              }
            >
              Retry submission
            </button>
          </div>
        )}
        <div className="my-4 grid grid-cols-2 rounded-xl bg-ochre-soft p-1">
          <button
            onClick={() => setDirection("target_to_meta")}
            className={`min-h-11 rounded-lg ${direction === "target_to_meta" ? "bg-cream font-bold" : ""}`}
          >
            Igbo → {metaName}
          </button>
          <button
            onClick={() => setDirection("meta_to_target")}
            className={`min-h-11 rounded-lg ${direction === "meta_to_target" ? "bg-cream font-bold" : ""}`}
          >
            {metaName} → Igbo
          </button>
        </div>
        <article className="rounded-[2rem] bg-cream p-7 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[.18em] text-terracotta">
            {session.unit_title}
          </p>
          <h1 className="mt-8 text-center font-display text-4xl leading-tight text-indigo-deep">
            {item.prompt}
          </h1>
          {session.mode === "quiz" ? (
            <QuizFeedback
              key={`${direction}-${item.id}`}
              choices={(item.options ?? []).map((option) => ({
                label: option.text,
                isCorrect: option.is_correct,
              }))}
              onSelect={(choice) => void record(choice.isCorrect)}
              onContinue={() => void advance()}
              disabled={advancing}
            />
          ) : (
            <Reveal
              mode={session.mode}
              item={item}
              revealed={revealed}
              onReveal={() => setRevealed(true)}
              onRate={(value) => void advance(value)}
              disabled={advancing}
            />
          )}
          <div className="mt-7 flex flex-wrap justify-between gap-3">
            <AudioButton url={item.audio_url} state={item.audio_state} />
            <FlagSheet key={item.id} contentId={item.id} metaLanguage={meta} />
          </div>
        </article>
      </div>
    </main>
  );
}

function Reveal({
  mode,
  item,
  revealed,
  onReveal,
  onRate,
  disabled,
}: {
  mode: string;
  item: StudyItem;
  revealed: boolean;
  onReveal: () => void;
  onRate: (correct: boolean) => void;
  disabled: boolean;
}) {
  if (!revealed)
    return (
      <button
        type="button"
        onClick={onReveal}
        className="mt-8 min-h-12 w-full rounded-xl bg-indigo-deep font-bold text-cream"
      >
        Reveal translation
      </button>
    );
  return (
    <div className="mt-8 animate-[fade_.25s_ease-out]">
      <p className="text-center text-xl font-semibold">{item.answer}</p>
      {item.literal_translation && (
        <p className="mt-4 text-muted">
          <strong>Literally:</strong> {item.literal_translation}
        </p>
      )}
      {mode === "phrase_practice" && item.example_sentence && (
        <div className="mt-5 rounded-xl bg-ochre-soft p-4">
          <p className="font-display text-xl">{item.example_sentence}</p>
          {item.example_translation && (
            <p className="mt-2">{item.example_translation}</p>
          )}
        </div>
      )}
      {mode === "proverbs" && item.cultural_note && (
        <section className="mt-6 max-w-prose border-t border-sand pt-5 text-[1.05rem] leading-8">
          <h2 className="font-display text-xl text-indigo-deep">
            Cultural context
          </h2>
          <p className="mt-2 whitespace-pre-wrap">{item.cultural_note}</p>
        </section>
      )}
      <div className="mt-7 grid grid-cols-2 gap-3">
        <button
          disabled={disabled}
          onClick={() => onRate(false)}
          className="min-h-12 rounded-xl border border-terracotta font-bold"
        >
          Still learning
        </button>
        <button
          disabled={disabled}
          onClick={() => onRate(true)}
          className="min-h-12 rounded-xl bg-indigo-deep font-bold text-cream"
        >
          I knew it
        </button>
      </div>
    </div>
  );
}
