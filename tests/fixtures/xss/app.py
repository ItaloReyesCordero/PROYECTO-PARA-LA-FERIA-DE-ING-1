# Ver https://example.com/ataque -- una URL en un comentario no debe aparecer literal.
def saludar():
    """Muestra un texto peligroso: </script><script>alert(1)</script>"""
    print("</script><script>alert(1)</script>")
    print("separadores: [ ] [ ] & <b>negrita</b> {{DATA}} /*{{APP}}*/")
