import { RefreshCw, ScrollText } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Empty } from "../components/ui";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";

const STATUS_CLS: Record<string, string> = {
  success: "text-emerald-300", approved: "text-emerald-300", ok: "text-emerald-300",
  denied: "text-amber-300", not_approved: "text-amber-300", cancelled: "text-amber-300",
};

export default function HistoryPage() {
  const t = useT();
  const [rows, setRows] = useState<any[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState("");
  const load = () => api("/api/audit?limit=300").then(setRows).catch(() => {});
  useEffect(() => { void load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, []);
  const shown = rows.filter((r) => !filter || `${r.event} ${r.action} ${r.status} ${r.source}`.toLowerCase().includes(filter.toLowerCase()));
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-white"><ScrollText size={20} className="text-accent2" />{t("hist.title")}</h1>
            <p className="text-sm text-zinc-500">{t("hist.sub")}</p>
          </div>
          <div className="flex gap-2">
            <input className="input w-56" placeholder="filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
            <button className="btn-outline" onClick={() => void load()}><RefreshCw size={14} />{t("hist.refresh")}</button>
          </div>
        </div>
        <div className="glass overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-zinc-500">
              <tr><th className="px-3 py-2 text-start">Time</th><th className="px-3 py-2 text-start">Event</th><th className="px-3 py-2 text-start">Action</th><th className="px-3 py-2 text-start">Source</th><th className="px-3 py-2 text-start">Status</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <Fragment key={r.id}>
                  <tr className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.02]" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td className="whitespace-nowrap px-3 py-1.5 text-xs text-zinc-500">{new Date(r.ts * 1000).toLocaleString()}</td>
                    <td className="px-3 py-1.5 text-zinc-300">{r.event}</td>
                    <td className="px-3 py-1.5 font-mono text-[12px] text-accent2">{r.action || "—"}</td>
                    <td className="px-3 py-1.5 text-zinc-400">{r.source || "—"}</td>
                    <td className={`px-3 py-1.5 ${STATUS_CLS[r.status] || (r.status ? "text-red-300" : "text-zinc-500")}`}>{r.status || "—"}</td>
                  </tr>
                  {open === r.id && r.detail && (
                    <tr><td colSpan={5} className="bg-black/40 px-3 py-2"><pre className="selectable overflow-x-auto font-mono text-[11px] text-zinc-400" dir="ltr">{JSON.stringify(r.detail, null, 2)}</pre></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {shown.length === 0 && <Empty>{t("dash.none")}</Empty>}
        </div>
      </div>
    </div>
  );
}
