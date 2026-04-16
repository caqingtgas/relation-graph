import type { JobPayload } from "../types";

export interface JobPoller {
  schedule(jobId: string, delayMs?: number): void;
  stop(): void;
}

export function createJobPoller(
  fetchStatus: (jobId: string) => Promise<JobPayload>,
  onUpdate: (payload: JobPayload) => void,
  onError: (error: Error) => void
): JobPoller {
  let currentJobId: string | null = null;
  let timer: number | null = null;

  function clear() {
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
  }

  async function pollOnce() {
    if (!currentJobId) {
      return;
    }
    try {
      const payload = await fetchStatus(currentJobId);
      onUpdate(payload);
    } catch (error) {
      clear();
      currentJobId = null;
      onError(error as Error);
    }
  }

  return {
    schedule(jobId: string, delayMs = 0) {
      currentJobId = jobId;
      clear();
      timer = window.setTimeout(() => {
        void pollOnce();
      }, delayMs);
    },
    stop() {
      clear();
      currentJobId = null;
    }
  };
}
