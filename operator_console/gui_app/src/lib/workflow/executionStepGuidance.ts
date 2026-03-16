export type ExecutionGuidanceKey = "ingest" | "plan" | "apply" | "canonical" | "tag";

export interface StepGuidanceSection {
  title: string;
  content: string;
}

export interface ExecutionStepGuidance {
  description: string;
  sections: StepGuidanceSection[];
}

export const executionStepGuidance: Record<ExecutionGuidanceKey, ExecutionStepGuidance> = {
  ingest: {
    description:
      "Register the target folder in the system so the rest of the pipeline can reason about the files it contains.",
    sections: [
      {
        title: "What this step does",
        content:
          "Ingest scans the folder you choose and records what files are present. Earlier workflows may have felt like they started later, but this step is explicit because the system needs a current inventory before it can plan anything safely.",
      },
      {
        title: "Before you run",
        content:
          "Pick the folder you want the system to inspect. In guided use, ingest is the true starting point because every later stage depends on the system having a current picture of the files in scope.",
      },
      {
        title: "What success looks like",
        content:
          "You see a plain-English summary of whether the folder introduced brand-new material, refreshed already known files, or surfaced duplicate matches the system already understands.",
      },
      {
        title: "Risk level",
        content:
          "This step updates the system record of what files exist in the selected folder. It does not move, rename, or reorganize files yet.",
      },
    ],
  },
  plan: {
    description:
      "Prepare the system's proposed decisions for the files you just ingested, without moving or renaming anything yet.",
    sections: [
      {
        title: "What this step does",
        content:
          "Plan looks at the folder you already ingested and works out what the system would do next, such as duplicate handling and file organization decisions.",
      },
      {
        title: "Before you run",
        content:
          "Use the same folder you already inspected with ingest so planning reflects the material you actually mean to organize. There is nothing extra to configure for the normal guided path beyond confirming you are ready for the next stage.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a saved plan with a run ID and a plain-English summary. That saved reference is what later apply work uses when it is time to carry out the plan.",
      },
      {
        title: "Risk level",
        content:
          "This step saves planning state in the system so later stages know what to do, but it does not yet move files or change canonical selections.",
      },
    ],
  },
  apply: {
    description:
      "Make the saved plan real so the changes prepared in planning are actually carried out.",
    sections: [
      {
        title: "What this step does",
        content:
          "Apply is the point where the workflow stops preparing and starts making real changes. The system uses a saved plan reference to carry out the work that planning prepared.",
      },
      {
        title: "Before you run",
        content:
          "Confirm you have selected the saved plan you actually want to execute. This is the step where a reviewed plan becomes real file and ledger work.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a plain-English summary of how many planned actions were carried out, how many moves happened, and whether any errors were reported. After this step, the pipeline can safely recalculate canonical selections against the new state.",
      },
      {
        title: "Risk level",
        content:
          "This step makes real file and ledger changes. It is the stage where the process stops being preparatory and starts carrying out the saved plan.",
      },
    ],
  },
  canonical: {
    description:
      "Choose which file becomes the main version after apply so later steps know which version to keep referring to.",
    sections: [
      {
        title: "What this step does",
        content:
          "This step chooses which file the system will treat as the main version going forward. Later views and enrichment use that chosen version instead of treating all duplicates equally.",
      },
      {
        title: "Before you run",
        content:
          "Run this after the main organize work has already settled so the chosen-version decisions are based on the post-apply state you actually want to keep.",
      },
      {
        title: "What success looks like",
        content:
          "You receive a plain-English summary of how many chosen-version decisions changed, how many updates were applied, and whether any failed.",
      },
      {
        title: "Risk level",
        content:
          "This step changes which file the system treats as the chosen version. It does not move files, but it does change which version later steps and views will prefer.",
      },
    ],
  },
  tag: {
    description:
      "Optionally add searchable tags and metadata to the chosen media items once the main organization work is complete.",
    sections: [
      {
        title: "What this step does",
        content:
          "Tag enrichment adds or refreshes metadata for the chosen media items. This can make later browsing, search, and discovery easier without changing the organization decisions you already made.",
      },
      {
        title: "Before you run",
        content:
          "Use this after the main organize work already looks right. If you would rather finish structural review first, you can leave enrichment for later without undoing earlier steps.",
      },
      {
        title: "What success looks like",
        content:
          "The library gains richer searchable detail, which can improve later discovery, browsing, and filtering without changing the structural decisions you already approved.",
      },
      {
        title: "Risk level",
        content:
          "This is downstream follow-up work. It builds on the current canonical set and does not undo ingest, planning, apply, or chosen-version decisions.",
      },
    ],
  },
};
