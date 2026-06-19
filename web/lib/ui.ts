export function verdictClass(v: string): string {
  if (v === "conforme") return "bg-green-100 text-green-800";
  if (v === "partiel") return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800"; // manquant
}

export function obligationClass(o: string): string {
  if (o === "obligatoire") return "bg-slate-200 text-slate-800";
  if (o === "souhaité") return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-600"; // optionnel
}

export function docStatusClass(s: string): string {
  if (s === "ready") return "bg-green-100 text-green-800";
  if (s === "failed") return "bg-red-100 text-red-800";
  return "bg-amber-100 text-amber-800"; // pending / processing
}
