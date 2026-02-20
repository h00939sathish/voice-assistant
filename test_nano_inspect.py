
try:
    from nanowakeword import utils
    print(f"utils: {utils}")
    
    if hasattr(utils, 'download_files'):
        obj = getattr(utils, 'download_files')
        print(f"download_files type: {type(obj)}")
        print(f"download_files dir: {dir(obj)}")
    else:
        print("Attribute download_files not found in utils")

except Exception as e:
    print(f"Error: {e}")
