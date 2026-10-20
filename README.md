# GIMP Spot Heal — maska jednego ruchu

Eksperymentalna gałąź **`feature/mask-area-healing`**, utworzona bezpośrednio
z `main` (commit `69c9901`). Przeznaczona dla **GIMP 2.10.36 / Windows**.

## Zasada działania

1. Przytrzymujesz LPM i malujesz obszar do usunięcia. Klik tworzy kółko,
   przeciągnięcie — pas, a ruch zygzakiem pozwala wypełnić plamę.
2. **Puszczenie LPM kończy maskę i automatycznie uruchamia naprawę.** Nie ma
   osobnego przycisku zatwierdzania zaznaczenia. Kolejny ruch to kolejna naprawa.
3. Program dobiera jedną przesuniętą próbkę dla całej maski i łączy ją z obrazem
   jednym rozwiązaniem Poissona. Nie wywołuje narzędzia Healing dla kolejnych punktów.

Obszar wyznacza suma okrągłych pędzli prowadzonych po całej ścieżce, także między
zdarzeniami myszy. Narysowanie samego zamkniętego obrysu zaznacza pas obrysu,
nie jego wnętrze. Żeby zaznaczyć plamę, zamaluj ją w jednym ruchu lub użyj
odpowiednio dużego pędzla.

## Dobór próbki

- Dla wydłużonych masek wyszukiwanie zaczyna się w poprzek głównego kierunku
  obszaru (analiza kształtu maski), z niewielką preferencją takich kierunków.
- Dla zwartych obszarów sprawdzane są kierunki wokół maski. Inne kierunki są
  dostępne również dla rys, jeśli zapewniają lepsze dopasowanie.
- W każdym kierunku odległość rośnie, aż znajdzie się miejsce dla całej próbki.
  Sprawdzane są też dalsze położenia. Źródło musi mieścić się w obrazie.
- Kontrola przecięcia używa **dokładnej maski powiększonej o margines 2 px**,
  a nie tylko jej środka lub prostokąta. Pozwala to korzystać z sąsiedztwa
  zakrzywionych rys bez kopiowania bieżącego obszaru naprawy.
- Bezpieczne próbki są porównywane na maksymalnie 96 punktach prawdziwej
  zewnętrznej granicy maski. Ocena uwzględnia wzór różnic koloru, stałą różnicę
  koloru i odległość. RGB samej skazy nie jest używane do oceny dopasowania.
- Jedno przesunięcie obowiązuje dla całego obszaru. Nie ma lokalnego doboru
  osobnej próbki dla każdego fragmentu maski ani funkcji przełączania strony.

## Łączenie całego obszaru

Solver zachowuje gradienty przesuniętej próbki i dopasowuje rozwiązanie do
oryginalnych pikseli wokół maski (warunek brzegowy Dirichleta). Obliczenia odbywają
się w liniowym RGB, z założeniem transferu sRGB. Nie stosujemy zamalowania średnim
kolorem ani dodatkowego low-passu.

Wynik zmienia wyłącznie RGB pikseli maski; poza nią obraz i alfa pozostają
niezmienione. Inna próbka może dać inny wynik tekstury. Duże skazy przecinające
krawędzie obiektów oraz sąsiednie skazy w źródle mogą nadal powodować artefakty:
algorytm nie rozpoznaje semantycznie zawartości zdjęcia.

## Instalacja na Windows

1. Sprawdź **Filtry → Python-Fu → Konsola**. Wtyczka wymaga Pythona 2.7 / PyGTK
   z instalacji GIMP-a; nie wymaga NumPy, OpenCV ani Resynthesizera.
2. Pobierz **`legacy/spot-heal-mask-210.py`** z tej gałęzi przez **Download raw file**.
   To gotowy pojedynczy plik, zawierający algorytm i okno.
3. Skopiuj go do folderu wtyczek użytkownika, typowo:
   `%APPDATA%\GIMP\2.10\plug-ins`. Faktyczną ścieżkę sprawdzisz w
   **Edycja → Preferencje → Foldery → Wtyczki**.
4. Uruchom ponownie GIMP-a, otwórz zdjęcie i wyszukaj klawiszem `/`
   **Spot Heal - maska**. Polecenie jest też w Filtry → Enhance / Uwydatnianie.

Nazwa pliku i polecenia są inne niż w dotychczasowym prototypie. To właśnie
**Spot Heal - maska** uruchamia nowy wariant.

## Sterowanie

| Czynność | Sterowanie |
| --- | --- |
| Malowanie maski | Przytrzymany LPM; podgląd na zdjęciu |
| Naprawa całej maski | Automatycznie po puszczeniu LPM |
| Kolejne źródło ostatniej naprawy | Inna probka |
| Cofnięcie całego ruchu | Cofnij / Ctrl+Z |
| Średnica pędzla | Pole 1–128 px oryginalnego zdjęcia |
| Powiększenie wokół kursora | Kółko, poza malowaniem |
| Przesuwanie widoku | Środkowy przycisk myszy, poza malowaniem |
| Widok całości / oryginalna skala | Dopasuj / 100% |
| Zachowanie kopii warstwy po całej sesji | Zastosuj |
| Odrzucenie całej sesji | Anuluj |

**Zastosuj nie kończy zaznaczania maski** — zamyka całą sesję i zachowuje wynik
w dokumencie. Każda maska jest naprawiana wcześniej, po puszczeniu LPM.

Inna probka zachowuje maskę, wybiera kolejne źródło z zapisanej listy i rozwiązuje
cały obszar ponownie. Powtórzenia nie dodają wpisów cofania. Ctrl+Z przywraca stan
sprzed całego ruchu, a wcześniejsze naprawy pozostają zachowane. W razie błędu
obliczeń lub zapisu poprzedni wynik jest przywracany.

## Ograniczenia pierwszej wersji

- Obraz RGB, 8-bit gamma sRGB (precyzja GIMP 150). Inne precyzje są odrzucane
  bez konwersji dokumentu. Dla zdjęć 16/32-bit ewentualną konwersję rób na kopii.
- Jedna zwykła warstwa, bez maski i zaznaczenia, offset 0,0; do 32 megapikseli.
- Maksymalnie 25000 pikseli maski, prostokąt ruchu do 1000000 pikseli. Większy
  obszar wymaga podzielenia na ruchy; obliczenia dużych masek mogą trwać dłużej.
- Pędzel musi pozostawić co najmniej jeden piksel oryginalnego obrazu przy brzegu.
- Nieprzezroczysta maska i jej otoczenie; kanał alfa nie jest rekonstruowany.
- Budżet cofania 128 MiB dla zapisów przed / po naprawach; najstarsze są usuwane.
- Podgląd pokazuje samą wybraną warstwę i nie zapewnia zarządzania kolorem monitora
  ani soft proofingu. Obliczenia zakładają sRGB; inne profile należy odpowiednio
  przekonwertować przed porównaniem kolorystycznym.
- W czasie obliczeń sterowanie i zamknięcie okna są chwilowo blokowane, aby nie
  nakładać operacji. Rozwiązanie niespełniające wymaganej dokładności jest odrzucane.

## Weryfikacja i rozwój

Automatyczne testy obejmują maskę punktu / linii / plamy, wykluczenie nakładania,
odtwarzanie syntetycznej tekstury z różnicą oświetlenia, zachowanie pikseli poza
maską, pojedyncze uruchomienie solvera po puszczeniu LPM, alternatywne źródła,
cofanie oraz przywracanie stanu po błędzie zapisu.

Testy kontrolera wykonują prawdziwy algorytm i solver; GIMP oraz GTK są atrapami.
Okno na Windows i efekty na rzeczywistych zdjęciach wymagają próby w GIMP-ie.

```sh
python tools/build_plugin.py
python -m unittest discover -s tests -v
python tools/build_plugin.py --check
```

Edytuj `src/mask_core.py` i `src/session_210.py`, następnie odtwórz gotowy plik
poleceniem budowania. CI uruchamia testy na Pythonie 3.12 i 2.7 oraz sprawdza
składnię i zgodność samodzielnego pliku ze źródłami.
