# Browser / HEVC Decode Test

1. Otworz panel lokalnie.
2. Wejdz w `Podglad na zywo`.
3. Ustaw aktywne streamy na `1`.
4. Otworz H9C SUB i zostaw go na 2 minuty.
5. Otworz Menedzer zadan Windows.
6. Zapisz CPU, GPU Video Decode, GPU 3D, RAM i siec.
7. Powtorz dla 2, 4 i 6 aktywnych streamow.

Interpretacja:

- Jesli GPU Video Decode prawie nie rosnie, a CPU rosnie mocno, HEVC/H.265 prawdopodobnie dekoduje sie software'owo.
- Jesli jeden kafelek jest stabilny, a 4-6 kafelkow laguje, limit aktywnych streamow albo HEVC decode jest wazniejszy niz sama kamera.
- Jesli FFmpeg/go2rtc sa stabilne, a panel laguje, szukaj przyczyny w przegladarce, dekodowaniu albo liczbie aktywnych kafelkow.
