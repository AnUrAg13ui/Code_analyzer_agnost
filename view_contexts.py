import os
import glob
import sys

# ── 📁 CONTEXT VIEWER ───────────────────────────────────────────────
# Reads and prints the agent context files dumped by the analysis pipeline.
# Run this AFTER triggering an analysis via the webhook or API.
# ────────────────────────────────────────────────────────────────────

DUMP_DIR = "agent_contexts"

def view_contexts():
    if not os.path.isdir(DUMP_DIR):
        print(f"❌ Directory '{DUMP_DIR}/' not found.")
        print("💡 Trigger a PR analysis first so the pipeline generates the context files.")
        return

    context_files = sorted(glob.glob(os.path.join(DUMP_DIR, "*.txt")))

    if not context_files:
        print(f"⚠️  No context files found in '{DUMP_DIR}/'.")
        return

    show_full = "--full" in sys.argv

    print("=" * 100)
    print(f"  📂 AGENT CONTEXT VIEWER — {len(context_files)} file(s) found in '{DUMP_DIR}/'")
    print("=" * 100)

    for i, file_path in enumerate(context_files, 1):
        filename = os.path.basename(file_path)
        agent_label = filename.replace("_context.txt", "").upper()

        print(f"\n[{i}/{len(context_files)}] 🤖 Agent: {agent_label}")
        print(f"    File : {file_path}")
        print("-" * 100)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                print("   (Empty — no prompt context was captured for this agent)")
            else:
                lines = content.splitlines()
                if not show_full and len(lines) > 60:
                    print("\n".join(lines[:60]))
                    print(f"\n... [{len(lines) - 60} more lines hidden. Run with --full to see everything] ...")
                else:
                    print(content)
        except Exception as e:
            print(f"   ❌ Could not read file: {e}")

        print("\n" + "#" * 100)

    print(f"\n✅ Done. Showing {'full' if show_full else 'truncated (60 lines)'} view.")
    print("💡 Tip: Run  'python view_contexts.py --full'  to see the complete prompts.\n")


if __name__ == "__main__":
    view_contexts()
