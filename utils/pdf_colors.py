def color_to_hex(v):
    if v is None:
        return "#000000"
    if isinstance(v, (list, tuple)):
        if len(v) == 0:
            return "#000000"
        if len(v) == 1:
            g = int(max(0.0, min(1.0, float(v[0]))) * 255)
            return f"#{g:02x}{g:02x}{g:02x}"
        if len(v) >= 3:
            r = int(max(0.0, min(1.0, float(v[0]))) * 255)
            g = int(max(0.0, min(1.0, float(v[1]))) * 255)
            b = int(max(0.0, min(1.0, float(v[2]))) * 255)
            return f"#{r:02x}{g:02x}{b:02x}"
    if isinstance(v, int):
        if v == 0:
            return "#000000"
        return f"#{(v>>16)&0xFF:02x}{(v>>8)&0xFF:02x}{v&0xFF:02x}"
    if isinstance(v, float):
        g = int(max(0.0, min(1.0, v)) * 255)
        return f"#{g:02x}{g:02x}{g:02x}"
    return "#000000"



def rgb_to_hex(rgb): return "#{:02x}{:02x}{:02x}".format(int(rgb[0]),int(rgb[1]),int(rgb[2]))
def int_color_to_hex(v):
    if not isinstance(v, int): return "#000000"
    return "#{:02x}{:02x}{:02x}".format((v>>16)&0xFF,(v>>8)&0xFF,v&0xFF)
