from komickers.config import update_config
from komickers.exceptions import ConfigError


def config_menu():
    print("\n================= CONFIGURATION MENU =================\n")
    print(
        "Please give your preference for each of these fields (for extra configuration, checkout the TOML file in .config)"
    )
    print(
        "Any blank fields with '!' will be filled with their respective default values, and empty inputs will keep its current value:\n"
    )

    tmp_dir = input("Temp Files Directory: ")
    credentials_dir = input("Credentilas Directory: ")
    token_dir = input("Google API Token Directory: ")
    downloads_dir = input("Downloads Directory: ")
    download_manager = input("Download Manager (surge, uget, wget2): ")
    email_address = input("Email Address: ")

    try:
        update_config(
            tmp_dir=tmp_dir,
            credentials_dir=credentials_dir,
            token_dir=token_dir,
            downloads_dir=downloads_dir,
            download_manager=download_manager,
            email_address=email_address,
        )
        print("\nSuccessfully updated config file")
        print("======================================================\n")
    except ConfigError as ce:
        print(f"Failed to update config: {ce}")
        print("======================================================\n")
