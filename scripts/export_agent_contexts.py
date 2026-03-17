import asyncio
import argparse
import sys
import os

# Ensure the root directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.provider_factory import get_provider
from services.context_builder import ContextBuilder


async def main(owner: str, repo: str, pr_number: int, output_file: str, agent: str):
    
    # Initialize provider
    provider = get_provider("github")
    if not provider:
        print("Error: GitHub provider could not be initialized. Is GITHUB_TOKEN set?")
        return

    builder = ContextBuilder(provider)

    print(f"Fetching data for {owner}/{repo} PR #{pr_number}...")

    try:
        pr_ctx = await builder.build(owner, repo, pr_number)
    except Exception as e:
        print(f"Failed to fetch PR: {e}")
        await provider.close()
        return

    if not pr_ctx.files:
        print("No changed files found in this PR (or they were filtered).")
        await provider.close()
        return

    with open(output_file, "w", encoding="utf-8") as f:

        f.write(f"PR CONTEXT EXPORT: {owner}/{repo} PR #{pr_number}\n")
        f.write(f"{'='*80}\n\n")

        for file_ctx in pr_ctx.files:

            fp = file_ctx['file_path']
            f.write(f"FILE: {fp}\n")
            f.write(f"{'-'*40}\n\n")

            if agent == "bug_detector":

                f.write("--- [BUG DETECTOR AGENT] ---\n")
                f.write(ContextBuilder.build_bug_detector_fragment(file_ctx))
                f.write("\n\n")

            elif agent == "rules_checker":

                f.write("--- [RULES CHECKER AGENT] ---\n")
                f.write(ContextBuilder.build_rules_checker_fragment(file_ctx))
                f.write("\n\n")

            elif agent == "git_history":

                f.write("--- [GIT HISTORY AGENT] ---\n")
                f.write(ContextBuilder.build_git_history_fragment(file_ctx))
                f.write("\n\n")

            elif agent == "past_pr":

                f.write("--- [PAST PR AGENT] ---\n")
                f.write(ContextBuilder.build_past_pr_fragment(file_ctx))
                f.write("\n\n")

            elif agent == "comment_verifier":

                f.write("--- [COMMENT VERIFIER AGENT] ---\n")
                f.write(ContextBuilder.build_comment_verifier_fragment(file_ctx))
                f.write("\n\n")

            else:
                print(f"Unknown agent: {agent}")
                break

            f.write(f"{'='*80}\n\n")

    print(f"✅ Context extraction complete. Saved to: {output_file}")

    await provider.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Export agent context from PR")

    parser.add_argument("owner", help="GitHub repo owner")
    parser.add_argument("repo", help="GitHub repo name")
    parser.add_argument("pr_number", type=int, help="PR number")

    parser.add_argument(
        "--agent",
        default="bug_detector",
        help="Agent type (bug_detector, rules_checker, git_history, past_pr, comment_verifier)"
    )

    parser.add_argument(
        "--output",
        default="agent_context.txt",
        help="Output file path"
    )

    args = parser.parse_args()

    asyncio.run(main(args.owner, args.repo, args.pr_number, args.output, args.agent))