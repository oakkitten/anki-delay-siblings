import os
import subprocess
import shlex
import re
from pathlib import Path
from textwrap import dedent


def run(command: str) -> str:
    return (
        subprocess.run(shlex.split(command), capture_output=True, check=True)
                  .stdout
                  .decode()
    )


def get_aqt_version(pip_output: str) -> str:
    return re.match(r"aqt \((2.1.[a-z0-9]+)\)", pip_output).group(1)


def last_bit(version: str) -> str:
    return version.split(".")[-1]


def remove_two_edge_newlines(text: str) -> str:
    if text.startswith("\n"):
        text = text[1:]
    if text.endswith("\n"):
        text = text[:-1]
    return text


# Inserts into `text` before line that matches `line_re`, additional lines.
# These lines are dedented and then inserted on the same level as the matched line.
# One leading and one trailing newlines of addition, if any, are removed.
def insert_before_line(text: str, line_re: str, addition: str):
    lines = []
    for line in text.split("\n"):
        if re.search(line_re, line):
            leading_spaces = len(line) - len(line.lstrip())
            for new_line in remove_two_edge_newlines(dedent(addition)).split("\n"):
                if new_line.strip():
                    lines.append(" " * leading_spaces + new_line)
                else:
                    lines.append("")
        lines.append(line)
    return "\n".join(lines)


########################################################################################


def add_new_tox_env(text: str, version: str) -> str:
    tag = last_bit(version)
    text = insert_before_line(text, "py39-ankilatest", f"py39-anki{tag}qt{{5,6}}")
    return insert_before_line(text, "ankilatest: anki==", f"""
        anki{tag}qt{{5,6}}: anki=={version}
        anki{tag}qt5: aqt[qt5]=={version}
        anki{tag}qt6: aqt[qt6]=={version}\n
    """)


def add_new_matrix_include(text: str, version: str) -> str:
    tag = last_bit(version)
    return insert_before_line(text, "name: Latest Anki", f"""
        - name: Anki {version} (Qt5)
          python: 3.9
          environment: py39-anki{tag}qt5
        - name: Anki {version} (Qt6)
          python: 3.9
          environment: py39-anki{tag}qt6
    """)


def replace_prerelease_tox_env(tox_ini: str, version: str):
    return re.sub(
        r"ankilatest: (anki|aqt\[qt6])==2.1.[a-z0-9]+",
        fr"ankilatest: \1=={version}",
        tox_ini
    )


def replace_prerelease_matrix_include_name(main_yml: str, version: str):
    return re.sub(
        r"Latest Anki \(2.1.[a-z0-9]+\)",
        fr"Latest Anki ({version})",
        main_yml
    )


########################################################################################
########################################################################################


def upgrade():
    tox_ini_file = Path("tox.ini")
    main_yml_file = Path(".github/workflows/main.yml")
    github_env_file = Path(os.environ["GITHUB_ENV"])

    tox_ini = tox_ini_file.read_text()
    main_yml = main_yml_file.read_text()

    latest_anki = get_aqt_version(run("pip index versions aqt"))
    latest_anki_pre = get_aqt_version(run("pip index --pre versions aqt"))
    print(f":: latest Anki version: {latest_anki}")
    print(f":: latest pre-release Anki version: {latest_anki_pre}")

    add_new_env = not re.search(fr"=={latest_anki}\b", tox_ini)
    update_pre_env = not re.search(fr"ankilatest: anki=={latest_anki_pre}\b", tox_ini)

    if not add_new_env and not update_pre_env:
        return

    if add_new_env:
        print(f":: adding new test environment for Anki {latest_anki}")
        tox_ini = add_new_tox_env(tox_ini, latest_anki)
        main_yml = add_new_matrix_include(main_yml, latest_anki)

    if update_pre_env:
        print(f":: updating pre-release test environment with Anki {latest_anki_pre}")
        tox_ini = replace_prerelease_tox_env(tox_ini, latest_anki_pre)
        main_yml = replace_prerelease_matrix_include_name(main_yml, latest_anki_pre)

    tox_ini_file.write_text(tox_ini)
    main_yml_file.write_text(main_yml)

    ####################################################################################

    add_new_env_msg = f"Add new test environment for Anki {latest_anki}"
    update_pre_env_msg = f"Update pre-release test environment with Anki {latest_anki_pre}"

    if add_new_env and update_pre_env:
        pr_title = f"{add_new_env_msg}; {update_pre_env_msg}".replace("; U", "; u")
        commit_message = (
            f"Tests: add env {latest_anki}, update pre env {latest_anki_pre}"
            f"\n\n{add_new_env_msg}\n{update_pre_env_msg}"
        )
    elif add_new_env:
        pr_title = add_new_env_msg
        commit_message = f"Tests: add new environment for Anki {latest_anki}"
    else:
        pr_title = update_pre_env_msg
        commit_message = f"Tests: update pre-release env with Anki {latest_anki_pre}"

    with github_env_file.open("a") as github_env:
        github_env.write(f'PR_TITLE<<EOF\n{pr_title}\nEOF\n')
        github_env.write(f'COMMIT_MESSAGE<<EOF\n{commit_message}\nEOF\n')


if __name__ == "__main__":
    upgrade()
