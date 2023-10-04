"""
Config module which can always be checked regardless of if the CRT was successfully built, installed on system, or not.
"""

"""
Returns True if either _awscrt was installed in the local environment or loaded from the system. 
Otherwise returns False indicating that any other functions or modules in this library will also fail.
"""
def crt_wheel_installed():
    try:
        import _awscrt
        return True
    except Exception:
        return False