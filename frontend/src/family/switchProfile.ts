import { setActiveProfileId } from "../lib/activeProfile";
import { answerQueue } from "../study/answerQueueService";

/**
 * Switch the device to a child profile (or back to the parent with null).
 *
 * Offline answers are queued without saying whose they are, so they are sent
 * first, while the old profile is still selected. If that fails (offline) the
 * switch is refused and the caller shows a message; nothing is lost.
 */
export async function switchProfile(id: string | null): Promise<void> {
  await answerQueue.flush();
  setActiveProfileId(id);
  window.location.assign("/");
}
