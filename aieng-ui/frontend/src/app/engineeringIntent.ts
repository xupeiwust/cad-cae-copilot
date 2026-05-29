import { api } from "../api";
import type { EngineeringChatIntent } from "./workbenchHelpers";

export function detectEngineeringIntent(msg: string, hasCadResult: boolean): EngineeringChatIntent | null {
  const lower = msg.toLowerCase();

  const simulatePhrases = [
    "run simulation", "mesh and solve", "start simulation", "execute simulation",
    "run analysis", "run solver", "run the simulation", "start the simulation",
  ];
  if (simulatePhrases.some((text) => lower.includes(text))) return "simulate";
  if (lower.trim() === "simulate" || lower.startsWith("simulate ")) return "simulate";

  const setTargetPhrases = [
    "set max stress", "set max displacement", "set stress limit", "set displacement limit",
    "set stress target", "set displacement target", "stress limit", "displacement limit",
    "stress target", "displacement target", "add target", "set target", "design target",
    "stress must be", "displacement must be", "stress should be", "displacement should be",
    "stress <= ", "displacement <= ", "stress < ", "displacement < ",
  ];
  const targetMetricWords = ["stress", "displacement", "deflection", "von mises", "sigma"];
  const hasTargetValue = /\d+\s*(mpa|mm)\b/i.test(msg);
  if (
    setTargetPhrases.some((text) => lower.includes(text)) ||
    (hasTargetValue && targetMetricWords.some((word) => lower.includes(word)) &&
      (lower.includes("set") || lower.includes("limit") || lower.includes("target") ||
        lower.includes("must") || lower.includes("should") || lower.includes("<=") || lower.includes("<")))
  ) {
    return "set_target";
  }

  const changeMaterialPhrases = [
    "change material", "switch material", "use material", "try material",
    "change to ", "switch to ", "try with ", "use steel", "use aluminum", "use titanium",
    "use al6061", "use al7075", "use ti-6al", "use nylon", "material to ",
  ];
  if (
    changeMaterialPhrases.some((text) => lower.includes(text)) &&
    (lower.includes("material") || lower.includes("steel") || lower.includes("aluminum") ||
      lower.includes("titanium") || lower.includes("nylon") || lower.includes("al6061") ||
      lower.includes("al7075") || lower.includes("ti-6al"))
  ) {
    return "change_material";
  }

  const refineMeshPhrases = [
    "refine mesh", "finer mesh", "smaller mesh", "mesh to ", "mesh size",
    "mesh refinement", "increase mesh", "denser mesh",
  ];
  if (refineMeshPhrases.some((text) => lower.includes(text))) {
    return "refine_mesh";
  }

  const feaVerbs = ["set up", "setup", "configure", "prepare", "generate fea", "run fea", "start fea"];
  const feaNouns = [
    "fea", "fea setup", "finite element", "simulation setup", "structural analysis",
    "boundary condition", "mesh setup", "preprocessing", "pre-processing",
  ];
  if (feaVerbs.some((text) => lower.includes(text)) && feaNouns.some((noun) => lower.includes(noun))) {
    return "preprocess";
  }
  if (lower.includes("preprocess") || lower.includes("pre-process")) {
    return "preprocess";
  }

  const genPhrases = [
    "generate", "create a", "create the", "design a", "design the",
    "make a", "make the", "model a", "model the", "build a", "build the",
    "draw a", "draw the",
    "生成", "创建", "设计", "画一个", "画个", "画一", "做一个", "做个",
    "建模", "绘制", "画", "做",
  ];
  const partNouns = [
    "part", "bracket", "plate", "housing", "mount", "gear", "enclosure",
    "fixture", "block", "shaft", "flange", "cap", "cover", "holder",
    "beam", "rod", "body", "component", "bushing", "sleeve", "clamp", "adapter",
    "咖啡机", "机器", "设备", "产品", "零件", "部件", "组件", "模型", "机",
  ];
  if (genPhrases.some((text) => lower.includes(text)) && partNouns.some((noun) => lower.includes(noun))) {
    return "generate";
  }

  if (hasCadResult) {
    const refineTriggers = [
      "make", "increase", "decrease", "change", "add", "remove",
      "thicker", "taller", "wider", "longer", "shorter", "bigger", "smaller",
      "refine", "adjust", "update", "modify",
      "修改", "调整", "加厚", "加宽", "加长", "增大", "减小", "变薄",
      "更新", "优化", "改",
    ];
    if (refineTriggers.some((text) => lower.includes(text))) return "refine";
  }

  return null;
}

export async function resolveEngineeringIntent({
  selectedId,
  prompt,
  hasCadResult,
}: {
  selectedId: string | null;
  prompt: string;
  hasCadResult: boolean;
}): Promise<{ intent: EngineeringChatIntent; materialHint?: string; meshSizeMm?: number } | null> {
  if (selectedId) {
    try {
      const plan = await api.engineeringActionPlan(selectedId, prompt);
      const intent = String(plan.intent ?? "");
      const known: EngineeringChatIntent[] = [
        "generate", "refine", "preprocess", "simulate", "change_material", "refine_mesh", "set_target",
      ];
      if (known.includes(intent as EngineeringChatIntent)) {
        const extracted = (plan.extracted_inputs as Record<string, unknown> | undefined) ?? {};
        const meshSizeRaw = extracted.mesh_size_mm;
        const meshSizeMm = typeof meshSizeRaw === "number" ? meshSizeRaw : undefined;
        const materialHint = typeof extracted.material_hint === "string" ? extracted.material_hint : undefined;
        return { intent: intent as EngineeringChatIntent, materialHint, meshSizeMm };
      }
    } catch {
      // Keep the chat usable if the backend planner is unavailable.
    }
  }

  const fallback = detectEngineeringIntent(prompt, hasCadResult);
  return fallback ? { intent: fallback } : null;
}
