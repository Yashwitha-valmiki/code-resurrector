import os
import base64
import requests
import streamlit as st
from google import genai

# Open-weight Gemma 4 models served through the Gemini API (tried in order)
MODELS = ["gemma-4-26b-a4b-it", "gemma-4-31b-it"]
MAX_CHARS = 6000

st.set_page_config(page_title="Code Resurrector", page_icon="🔧")
st.title("🔧 Code Resurrector")
st.caption("Give it an abandoned GitHub repo. Open-weight Gemma explains what it did, "
           "why it died, and how to revive it.")


def secret_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")


api_key = secret_key()
if not api_key:
    api_key = st.sidebar.text_input("AI Studio API key", type="password")

repo_url = st.text_input("Public GitHub repo URL",
                         placeholder="https://github.com/owner/repo")


def parse_repo(url):
    parts = url.strip().rstrip("/").replace("https://github.com/", "").split("/")
    return (parts[0], parts[1]) if len(parts) >= 2 else (None, None)


def gh(path):
    r = requests.get(f"https://api.github.com{path}", timeout=20)
    r.raise_for_status()
    return r.json()


def read_file(owner, repo, path):
    try:
        data = gh(f"/repos/{owner}/{repo}/contents/{path}")
        return base64.b64decode(data["content"]).decode("utf-8", "ignore")[:MAX_CHARS]
    except Exception:
        return ""


def collect(owner, repo):
    info = gh(f"/repos/{owner}/{repo}")
    tree = gh(f"/repos/{owner}/{repo}/contents")
    names = [t["name"] for t in tree]
    wanted = ["README.md", "README.rst", "README.txt", "readme.md",
              "requirements.txt", "setup.py", "package.json", "pyproject.toml"]
    files = {n: read_file(owner, repo, n) for n in wanted if n in names}
    return {
        "description": info.get("description"),
        "language": info.get("language"),
        "last_pushed": info.get("pushed_at"),
        "archived": info.get("archived"),
        "open_issues": info.get("open_issues_count"),
        "stars": info.get("stargazers_count"),
        "top_level_files": names,
        "files": {k: v for k, v in files.items() if v},
    }


def ask_gemma(client, prompt):
    last_error = None
    for model in MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            return resp.text, model
        except Exception as e:
            last_error = e
    raise last_error


if st.button("Resurrect it 🔧") and repo_url:
    owner, repo = parse_repo(repo_url)
    if not owner:
        st.error("That doesn't look like a GitHub repo URL.")
    elif not api_key:
        st.error("Add your API key in the sidebar.")
    else:
        try:
            with st.spinner("Digging up the repo..."):
                facts = collect(owner, repo)
            st.subheader("What I found")
            st.json({k: v for k, v in facts.items() if k != "files"})

            prompt = (
                "You are a senior open-source maintainer helping revive an abandoned "
                "project. Use ONLY the facts below. If something is unknown, say so; "
                "do not invent details. Reply with these sections:\n"
                "1. What this project did (3 sentences)\n"
                "2. Why it probably stopped being maintained (evidence-based)\n"
                "3. What is likely broken today (old dependencies, outdated APIs)\n"
                "4. A 5-step revival plan a beginner could follow\n"
                "5. One modern alternative or improvement idea\n\n"
                f"REPO FACTS:\n{facts}"
            )
            client = genai.Client(api_key=api_key)
            with st.spinner("Gemma is reading the old code..."):
                text, used_model = ask_gemma(client, prompt)
            st.subheader("The revival report")
            st.write(text)
            st.caption(f"Written by open-weight model: {used_model}")
        except requests.HTTPError as e:
            st.error(f"GitHub problem: {e}. Check the URL is a public repo.")
        except Exception as e:
            st.error(f"Something failed: {e}")