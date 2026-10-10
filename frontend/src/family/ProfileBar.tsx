import { useEffect, useState } from "react";

import { useUiStrings } from "../i18n/useUiStrings";
import { useActiveProfileId } from "../lib/activeProfile";
import { apiFetch } from "../lib/api";
import type { ChildProfile, UserProfile } from "../lib/types";
import { BackToParent } from "./BackToParent";
import { switchProfile } from "./switchProfile";

/** Shows who is learning. Parents with children can switch between profiles. */
export function ProfileBar() {
  const strings = useUiStrings().family;
  const activeId = useActiveProfileId();
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [childName, setChildName] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (activeId) {
      void apiFetch<UserProfile>("/v1/me", { authenticated: true })
        .then((me) => active && setChildName(me.display_name ?? ""))
        .catch(() => undefined);
    } else {
      void apiFetch<ChildProfile[]>("/v1/me/children", { authenticated: true })
        .then((list) => active && setChildren(list))
        .catch(() => undefined);
    }
    return () => {
      active = false;
    };
  }, [activeId]);

  if (activeId)
    return (
      <section className="space-y-3 rounded-2xl bg-cream p-4 shadow-card">
        <p className="font-semibold text-indigo-deep">
          {strings.learningAs} {childName}
        </p>
        <BackToParent />
      </section>
    );
  if (children.length === 0) return null;
  return (
    <section className="rounded-2xl bg-cream p-4 shadow-card">
      <label className="grid gap-2 font-semibold text-indigo-deep">
        {strings.learningAs}
        <select
          value=""
          className="min-h-11 rounded-xl border border-sand bg-white px-3"
          onChange={(event) => {
            const id = event.target.value;
            if (!id) return;
            setMessage(null);
            void switchProfile(id).catch(() =>
              setMessage(strings.switchOffline),
            );
          }}
        >
          <option value="">{strings.myProfile}</option>
          {children.map((child) => (
            <option key={child.id} value={child.id}>
              {child.nickname}
            </option>
          ))}
        </select>
      </label>
      {message && <p role="alert">{message}</p>}
    </section>
  );
}
