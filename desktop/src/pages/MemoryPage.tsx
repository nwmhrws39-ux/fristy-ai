import { Brain, Download, Pencil, Plus, Trash2, Upload, Check, X, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Empty, Select } from "../components/ui";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";
import { toast } from "../lib/store";

const CATS = ["preference", "favorite_game", "frequent_app", "language", "project", "custom_command", "routine", "fact", "conversation_summary"];

export default function MemoryPage() {
  const t = useT();
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState({ category: "preference", key: "", value: "" });
  const [edit, setEdit] = useState<{ id: number; value: string } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const load = () => api(`/api/memory?${new URLSearchParams({ ...(filter ? { category: filter } : {}), ...(q ? { search: q } : {}) })}`).then(setItems).catch((e) => toast(e.message, "error"));
  useEffect(() => { void load(); }, [filter, q]);

  const add = async () => {
    try { await api("/api/memory", { body: draft }); setDraft({ ...draft, key: "", value: "" }); void load(); }
    catch (e) { toast((e as Error).message, "error", 6000); }
  };
  const save = async () => {
    if (!edit) return;
    try { await api(`/api/memory/${edit.id}`, { method: "PATCH", body: { value: edit.value } }); setEdit(null); void load(); }
    catch (e) { toast((e as Error).message, "error", 6000); }
  };
  const exportAll = async () => {
    const data = await api("/api/memory-export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = `fristy-memory-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    URL.revokeObjectURL(url);
  };
  const importFile = async (f: File) => {
    try { const r = await api("/api/memory-import", { body: JSON.parse(await f.text()) }); toast(`${r.imported} ✓`, "success"); void load(); }
    catch (e) { toast((e as Error).message, "error"); }
  };
  const clear = async () => {
    if (!window.confirm(t("mem.confirm_clear"))) return;
    await api("/api/memory", { method: "DELETE" }); void load();
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-white"><Brain size={20} className="text-accent2" />{t("mem.title")}</h1>
            <p className="text-sm text-zinc-500">{t("mem.sub")}</p>
          </div>
          <div className="flex gap-2">
            <button className="btn-outline" onClick={() => void exportAll()}><Download size={14} />{t("mem.export")}</button>
            <button className="btn-outline" onClick={() => file.current?.click()}><Upload size={14} />{t("mem.import")}</button>
            <input ref={file} type="file" accept="application/json" hidden onChange={(e) => e.target.files?.[0] && void importFile(e.target.files[0])} />
            <button className="btn-ghost text-red-300" onClick={() => void clear()}><Trash2 size={14} />{t("mem.clear")}</button>
          </div>
        </div>
        <div className="glass mb-4 grid grid-cols-[180px_1fr_2fr_auto] items-end gap-2 p-3">
          <Select value={draft.category} onChange={(v) => setDraft({ ...draft, category: v })} options={CATS.filter((c) => c !== "conversation_summary").map((c) => ({ value: c, label: c }))} />
          <input className="input" dir="auto" placeholder={t("mem.key")} value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} />
          <input className="input" dir="auto" placeholder={t("mem.value")} value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && void add()} />
          <button className="btn-primary" disabled={!draft.key || !draft.value} onClick={() => void add()}><Plus size={14} />{t("mem.add")}</button>
        </div>
        <div className="mb-3 flex gap-2">
          <div className="relative flex-1"><Search size={14} className="absolute start-2.5 top-2.5 text-zinc-500" /><input className="input ps-8" placeholder="…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <Select className="w-56" value={filter} onChange={setFilter} options={[{ value: "", label: "All categories" }, ...CATS.map((c) => ({ value: c, label: c }))]} />
        </div>
        <div className="glass divide-y divide-white/[0.05]">
          {items.length === 0 && <Empty>{t("mem.empty")}</Empty>}
          {items.map((m) => (
            <div key={m.id} className="flex items-start gap-3 px-4 py-3">
              <span className="chip mt-0.5 shrink-0">{m.category}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-zinc-200" dir="auto">{m.key}</div>
                {edit?.id === m.id ? (
                  <textarea className="input mt-1" dir="auto" rows={3} value={edit?.value ?? ""} onChange={(e) => setEdit({ id: m.id, value: e.target.value })} />
                ) : (
                  <div className="selectable whitespace-pre-wrap text-sm text-zinc-400" dir="auto">{m.value}</div>
                )}
                <div className="mt-1 text-[11px] text-zinc-600">{m.source} · {new Date(m.updated_at * 1000).toLocaleString()}</div>
              </div>
              {edit?.id === m.id ? (
                <><button className="btn-ghost h-8 w-8 p-0 text-emerald-300" onClick={() => void save()}><Check size={14} /></button>
                  <button className="btn-ghost h-8 w-8 p-0" onClick={() => setEdit(null)}><X size={14} /></button></>
              ) : (
                <><button className="btn-ghost h-8 w-8 p-0" title={t("mem.edit")} onClick={() => setEdit({ id: m.id, value: m.value })}><Pencil size={13} /></button>
                  <button className="btn-ghost h-8 w-8 p-0 text-zinc-500 hover:text-red-300" onClick={() => api(`/api/memory/${m.id}`, { method: "DELETE" }).then(load)}><Trash2 size={13} /></button></>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
