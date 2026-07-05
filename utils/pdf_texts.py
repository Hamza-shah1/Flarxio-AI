def pdf_map_font_to_css(pdf_font_name):
    name = pdf_font_name
    if "+" in name:
        name = name.split("+", 1)[1]
    n = name.lower().replace("-","").replace(" ","").replace("_","")

    if any(x in n for x in ["timesnew","timesroman","times","nimbusroman",
                              "palatino","garamond","bookman","georgia",
                              "newcentury","schoolbook","minion","caslon"]):
        return "'Times New Roman', Times, Georgia, serif"
    if any(x in n for x in ["helvetica","arial","nimbussans","liberation",
                              "freesans","myriad","calibri","tahoma","optima",
                              "gill","trebuchet","verdana","futura"]):
        return "Arial, Helvetica, sans-serif"
    if any(x in n for x in ["courier","nimbusmon","freemono","liberation",
                              "consolasmono","inconsolata","droidsans"]):
        return "'Courier New', Courier, monospace"
    if any(x in n for x in ["impact","haettenschweiler","compacta"]):
        return "Impact, 'Arial Narrow', sans-serif"
    if any(x in n for x in ["roman","serif","book"]):
        return "'Times New Roman', Times, serif"
    return "Arial, Helvetica, sans-serif"


