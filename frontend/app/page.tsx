import HealthStatus from "@/components/HealthStatus";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-50 px-6 font-sans dark:bg-black">
      <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
        Table Talk
      </h1>
      <p className="max-w-md text-center text-zinc-600 dark:text-zinc-400">
        Chat-based multi-CSV data analysis PoC. Scaffolding phase &mdash; chat
        UI arrives in a later phase.
      </p>
      <HealthStatus />
    </div>
  );
}
