import os
import subprocess


def open_notepad(voice):

    subprocess.Popen(
        ["notepad.exe"],
        shell=False
    )

    voice.speak("Opening Notepad.")


def open_calculator(voice):

    subprocess.Popen(
        ["calc.exe"],
        shell=False
    )

    voice.speak("Opening Calculator.")


def open_command_prompt(voice):

    subprocess.Popen(
        ["cmd.exe"],
        shell=False
    )

    voice.speak("Opening Command Prompt.")


def open_powershell(voice):

    subprocess.Popen(
        ["powershell.exe"],
        shell=False
    )

    voice.speak("Opening PowerShell.")


def open_file_explorer(voice):

    subprocess.Popen(
        ["explorer.exe"],
        shell=False
    )

    voice.speak("Opening File Explorer.")


def open_settings(voice):

    subprocess.Popen(
        ["cmd", "/c", "start", "ms-settings:"],
        shell=False
    )

    voice.speak("Opening Windows Settings.")


def open_task_manager(voice):

    subprocess.Popen(
        ["taskmgr.exe"],
        shell=False
    )

    voice.speak("Opening Task Manager.")


def lock_computer(voice):

    voice.speak("Locking the computer.")

    os.system(
        "rundll32.exe user32.dll,LockWorkStation"
    )


def shutdown_computer(voice):

    voice.speak(
        "Shutting down the computer."
    )

    os.system(
        "shutdown /s /t 5"
    )


def restart_computer(voice):

    voice.speak(
        "Restarting the computer."
    )

    os.system(
        "shutdown /r /t 5"
    )


def handle_application(command, voice):
    """Try to handle a Windows application-launch command. Returns True if handled."""

    # NOTEPAD
    if "notepad" in command:
        open_notepad(voice)
        return True

    # CALCULATOR
    if "calculator" in command or "calc" in command:
        open_calculator(voice)
        return True

    # COMMAND PROMPT
    if "command prompt" in command or command == "cmd":
        open_command_prompt(voice)
        return True

    # POWERSHELL
    if "powershell" in command:
        open_powershell(voice)
        return True

    # FILE EXPLORER
    if "file explorer" in command or "explorer" in command:
        open_file_explorer(voice)
        return True

    # SETTINGS
    if "settings" in command:
        open_settings(voice)
        return True

    # TASK MANAGER
    if "task manager" in command:
        open_task_manager(voice)
        return True

    return False


def handle_system(command, voice):
    """Try to handle a system power command. Returns True if handled."""

    # LOCK COMPUTER
    if "lock computer" in command:
        lock_computer(voice)
        return True

    # SHUTDOWN
    if "shutdown computer" in command:
        shutdown_computer(voice)
        return True

    # RESTART
    if "restart computer" in command:
        restart_computer(voice)
        return True

    return False
