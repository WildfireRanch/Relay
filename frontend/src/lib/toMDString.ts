export function toMDString(val: unknown): string {
  if (val == null) return "";
  if (typeof val === "string") return val;
  if (Array.isArray(val)) {
    return val.map((v) => toMDString(v)).join("\n\n");
  }
  if (typeof val === "object") {
    try {
      return "```json\n" + JSON.stringify(val, null, 2) + "\n```";
    } catch {
      return String(val);
    }
  }
  return String(val);
}
export default toMDString;
