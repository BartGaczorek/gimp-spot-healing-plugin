# GIMP Spot Healing Plugin

Eksperymentalna wtyczka do retuszu drobnych skaz jednym kliknięciem.
Źródło jest dobierane automatycznie z otoczenia, a naprawę wykonuje **Healing
GIMP-a** — z dopasowaniem przejścia, zamiast prostego wklejania pikseli.

## Status: prototyp 0.3 — próbkowanie prostopadłe w GIMP-ie 2.10

| GIMP | Plik / folder | Wymagania |
| --- | --- | --- |
| 2.10.36 Windows | `legacy/spot-heal-210.py` — jeden plik | Python-Fu / Python 2.7 i PyGTK z instalatora GIMP-a; zdjęcie RGB 8-bit sRGB |
| 3.x | folder `gimp-spot-heal` | Python 3 / GTK 3 dostarczane z GIMP-em |

Nie wymaga NumPy, OpenCV ani Resynthesizera.
Testy automatyczne obejmują dobór źródła i geometrię widoku. Uruchomienie okna,
wywołania GIMP/GEGL i jakość retuszu wymagają jeszcze sprawdzenia w działającym
GIMP-ie; nie zostały przetestowane w środowisku, w którym powstała ta wersja.
Kontrole Pythona 2.7 sprawdzają algorytm i składnię; nie emulują Windows, PyGTK
ani samego GIMP-a.

## Gałąź `feature/perpendicular-sources`

Zmiany w tej gałęzi dotyczą wariantu **GIMP 2.10.36 / Windows**. Dla linii źródło
jest wybierane wyłącznie w kierunku prostopadłym do wektora od początku do końca
ruchu. Dodano przycisk **Zmien strone**, działający na ostatnią naprawę, jeśli jest
ona linią i po przeciwnej stronie istnieje bezpieczne źródło. Wariant GIMP 3
zachowuje dotychczasowy dobór źródła w wielu kierunkach.

## Instalacja: GIMP 2.10.36 na Windows

1. Sprawdź, czy masz **Filtry → Python-Fu → Konsola**. Jeżeli nie, w instalacji
   brakuje aktywnej obsługi Python-Fu. Instalator GIMP-a 2.10.36 z gimp.org zawiera
   komponent Python; zmodyfikuj / ponów instalację z tym komponentem. Nie instaluj
   osobno najnowszego Pythona — ta wtyczka korzysta z Pythona 2.7 GIMP-a.
2. Z tej gałęzi repozytorium pobierz plik **`legacy/spot-heal-210.py`** przyciskiem
   **Download raw file** przy pliku. Nie zapisuj strony HTML GitHuba. Alternatywnie
   pobierz całe archiwum i wyjmij z folderu `legacy` tylko ten plik.
3. W GIMP-ie: **Edycja → Preferencje → Foldery → Wtyczki**. Skopiuj plik do
   zapisywalnego folderu użytkownika. Typowo jest to
   `%APPDATA%\GIMP\2.10\plug-ins` (można wkleić w pasek Eksploratora Windows).
   Plik umieść bezpośrednio w `plug-ins`, nie w `scripts`.
4. Uruchom ponownie GIMP-a. Otwórz zdjęcie i wybierz **Filtry → Uwydatnianie
   (Enhance) → Spot Heal 2.10…**. Możesz też użyć `/` i wyszukać „Spot Heal”.

Kopiowanie dotyczy tylko `spot-heal-210.py`; wspólny algorytm jest już w nim
zawarty. Nie trzeba kopiować pliku `session_210.py` ani instalować wariantu dla GIMP-a 3.

**Ważne dla wariantu 2.10:** obsługiwany jest obraz RGB o precyzji **8-bitowa
całkowita, gamma perceptualna (sRGB)**. Zwykły otwarty JPEG zazwyczaj spełnia ten
warunek. Obrazy 16/32-bit i 8-bit linear są odrzucane bez konwersji dokumentu.
Jeśli chcesz je przetestować, najpierw wykonaj kopię dokumentu i zmień precyzję
tej kopii w menu **Obraz → Precyzja**. To ograniczenie starego wariantu, który
używa interfejsu PixelRgn do podglądu i zapisów cofania.

Sterowanie jest takie samo jak poniżej: klik / krótki ruch LPM, zoom kółkiem,
przesuwanie ŚPM, Cofnij / Ctrl+Z. Okno początkowo dopasowuje widok zdjęcia,
a jego rozmiar mieści się w 85% rozdzielczości ekranu. Naprawa odbywa się na
automatycznej kopii warstwy. W wariancie 2.10 etykiety są bez polskich znaków.

## Instalacja: GIMP 3.x

1. Pobierz repozytorium: **Code → Download ZIP**, następnie rozpakuj archiwum.
2. W GIMP-ie otwórz **Preferencje → Foldery → Wtyczki** i znajdź swój zapisywalny
   folder użytkownika. To pewniejsza metoda niż zakładanie konkretnej ścieżki
   Windows / Linux / macOS.
3. Skopiuj do niego **cały folder `gimp-spot-heal`**, z oboma plikami:

   ```text
   plug-ins/
     gimp-spot-heal/
       gimp-spot-heal.py
       spot_core.py
   ```

4. Na Linuxie / macOS nadaj plikowi startowemu prawo wykonania:
   `chmod +x /pełna/ścieżka/gimp-spot-heal/gimp-spot-heal.py`.
5. Uruchom ponownie GIMP-a. Otwórz zdjęcie i wybierz
   **Filtry → Uwydatnianie (Enhance) → Spot Heal…**.
   Nazwa przetłumaczonej kategorii zależy od języka GIMP-a; polecenie można też
   znaleźć, wpisując „Spot Heal” w wyszukiwarce poleceń otwieranej klawiszem `/`.

## Obsługa

Wybierz jedną zwykłą warstwę RGB bez maski i aktywnych filtrów, usuń zaznaczenie.
Wtyczka automatycznie tworzy kopię tej warstwy. Widok pokazuje piksele wybranej
warstwy, a nie kompozycję wszystkich warstw.

| Czynność | Sterowanie |
| --- | --- |
| Usunięcie kropki | Jeden klik LPM |
| Krótki włos / rysa | Przeciągnięcie LPM; naprawa po puszczeniu przycisku |
| Średnica pędzla | Pole w pasku; wartość w pikselach zdjęcia, niezależna od zoomu |
| Powiększenie | Kółko myszy, wokół kursora; od 1% do 400% |
| Przesuwanie | Przytrzymaj środkowy przycisk myszy i przeciągnij |
| Widok całego zdjęcia | Dopasuj; początkowy widok, bez powiększania małych zdjęć |
| Oryginalny rozmiar pikseli | 100% |
| Cofnięcie kliknięcia lub całego ruchu | Cofnij / Ctrl+Z |
| Przełączenie źródła ostatniej linii (2.10) | Zmien strone; można przełączać wielokrotnie |
| Zachowanie retuszu | Zastosuj; kopia zostaje w dokumencie |
| Odrzucenie sesji | Anuluj / zamknięcie okna; kopia jest usuwana |

Ustaw pędzel tylko trochę większy od skazy. Włos zamaluj krótkim ruchem
wzdłuż jego przebiegu. Zbyt duży pędzel lub zbyt długi ruch utrudniają znalezienie
pasującego źródła. Nie ma automatycznego wykrywania całego włosa po jednym kliknięciu.

## Dobór źródła w wariancie 2.10

**Pojedynczy klik** zachowuje dotychczasowy dobór źródła wokół punktu.

**Linia** ma jeden kierunek od początku do końca ruchu. Program wyznacza do niego
prostopadłą i sprawdza kilka odległości po obu stronach. Dla poziomej linii źródło
leży wyłącznie nad nią lub pod nią; dla pionowej — wyłącznie po lewej lub prawej.
Każda strona ma własną najlepiej dopasowaną bezpieczną odległość. Pierwsza naprawa
wybiera stronę o niższym wyniku porównania otoczenia.

Kierunek i przesunięcie są stałe dla wszystkich punktów linii, również gdy ruch
jest łagodnie zakrzywiony. Nie wyznaczamy osobnej normalnej dla każdego punktu.
Pętla lub ruch z końcem bliżej niż 1 px od początku jest odrzucany.

### Wykluczenie obszaru naprawy

Program rzutuje całą ścieżkę na prostopadłą. Pas obejmujący przesuniętą ścieżkę
źródła musi być rozłączny z pasem naprawy, po uwzględnieniu promienia pędzla,
marginesu 2 px z każdej strony oraz zaokrąglania współrzędnych źródła w GIMP-ie.
Rzut odcinka mieści się między rzutami jego końców, więc test obejmuje także
obszar między zarejestrowanymi punktami. Chroni to całą powierzchnię prowadzonego
pędzla, a nie tylko środki odbić.

Test jest zachowawczy: przy mocnym zakrzywieniu może odrzucić również ścieżki,
które w rzeczywistości się nie przecinają. Bezpieczna próbka musi też mieścić
się w warstwie. Jeśli żadna strona nie spełnia warunków, obraz pozostaje bez zmian
i pojawia się komunikat o skróceniu linii / zmniejszeniu pędzla.

Dopasowanie tekstury ocenia 48 próbek na granicy prostokąta otaczającego ruch.
Porównywane są lokalne różnice koloru po odjęciu stałego przesunięcia kolorów,
z dodatkową karą za dużą różnicę koloru i odległość. Próbkowana przezroczystość
jest odrzucana. To heurystyka, a nie rozpoznawanie innych skaz.

### Zmien strone

Przycisk odtwarza stan sprzed ostatniej linii i wykonuje tę samą ścieżkę z próbką
po przeciwnej stronie. Odległości po obu stronach mogą się różnić, ponieważ dla
każdej strony wybierane jest najlepiej dopasowane bezpieczne źródło.

- Ponowne kliknięcie wraca do poprzedniej strony.
- Zachowana jest średnica pędzla użyta przy rysowaniu, nawet po zmianie pola rozmiaru.
- Wcześniejsze naprawy pozostają zachowane.
- Przełączenia nie tworzą osobnych wpisów cofania: Ctrl+Z usuwa całą ostatnią linię.
- Błąd podczas przełączania przywraca poprzedni wynik i poprzednio wybraną stronę.
- Po pojedynczym kliknięciu oraz przy braku źródła po drugiej stronie przycisk
  jest nieaktywny. Cofnięcie kliknięcia może ponownie udostępnić zmianę strony
  poprzedniej linii.
- Funkcja działa na ostatniej operacji; nie wybiera starszej linii spod kolejnych napraw.

Linia jest wykonywana jako zachodzące na siebie punkty natywnego Healing,
w odstępach do 20% średnicy (minimum 1 px), z limitem 4096 odbić. Nie stosujemy
dodatkowego low-passu. Obraz sprzed i po naprawie jest przechowywany w historii
8-bitowego wariantu 2.10; obie kopie liczą się do budżetu 128 MiB.

## Wariant GIMP 3

Zachowuje wyszukiwanie do 160 przesunięć wokół ruchu, z rozłącznymi prostokątami
źródła i naprawy. Nie ma przycisku zmiany strony. Naprawę wykonuje `Gimp.heal`,
a kopie do cofania są zapisywane w formacie warstwy, bez redukcji precyzji do 8 bitów.

## Ograniczenia prototypu

- Maksymalnie 32 megapiksele na warstwę. Podgląd przechowuje pełną warstwę
  w pamięci i jest odświeżany po naprawie; duże zdjęcia mogą działać wolniej.
- Cofanie w oknie ma budżet 128 MiB; najstarsze zapisy są usuwane po jego
  przekroczeniu. Nie ma ponawiania (Redo).
- Przy krawędzi warstwy, przezroczystości albo braku źródła naprawa jest odrzucana.
- Brak obsługi masek, filtrów niedestrukcyjnych, grup i zaznaczeń.
- Warstwa musi mieć położenie (offset) 0, 0 względem płótna. Obsługa przesuniętych
  warstw zostanie dodana po sprawdzeniu współrzędnych natywnego Healing.
- Podgląd GTK nie ma pełnego zarządzania kolorem monitora / soft proofingu GIMP-a.
  Ostateczny kolor oceniaj w głównym oknie GIMP-a.
- Wynik dziedziczy tryb mieszania, krycie i położenie kopiowanej warstwy.
  Typowy przypadek to pojedyncza warstwa zdjęcia w trybie Normal, krycie 100%.
- Anulowanie usuwa kopię, ale operacja może pozostać w historii dokumentu.
- Zmiany w GIMP-ie są grupowane jako jedna sesja. W jej trakcie używaj cofania
  w oknie wtyczki. Po zatwierdzeniu można cofnąć całą sesję w GIMP-ie.

## Pierwsza próba i zgłaszanie błędów

Sprawdź na kopii zdjęcia: jasny punkt na gładkim tle, kurz na fakturze, krótki
włos, skazę przy krawędzi obiektu; obejrzyj wynik przy 100%. Sprawdź też pojedyncze
cofnięcie, cofnięcie całego ruchu, Anuluj i Zastosuj. W wariancie 2.10 sprawdź
poziomą, pionową i ukośną rysę, kilkukrotne Zmien strone, cofnięcie po przełączeniu,
linię przy brzegu zdjęcia oraz zmianę średnicy przed przełączeniem. Potem sprawdź zdjęcie 16-bitowe
i komunikat o braku obsługi warstwy przesuniętej względem płótna. Wariant 2.10
powinien odrzucić zdjęcie 16-bitowe, a wariant 3 obsługuje je bez zmiany precyzji.

Do zgłoszenia dodaj system, pełną wersję GIMP-a, rozmiar i precyzję obrazu,
średnicę pędzla, kroki odtworzenia oraz dokładny komunikat. Jeśli to możliwe,
dołącz niesensytywny wycinek zdjęcia przed i po naprawie.

## Rozwój

```sh
python -m unittest discover -s tests -v
python -m compileall -q gimp-spot-heal
python tools/build_legacy.py --check
```

`spot_core.py` jest zgodny z Pythonem 2.7 i 3. Kod okna 2.10 znajduje się w
`legacy/session_210.py`. Po zmianach wspólnego algorytmu lub tego okna uruchom
`python tools/build_legacy.py`, aby odtworzyć samodzielny `legacy/spot-heal-210.py`.
Nie edytuj wygenerowanego pliku ręcznie.

GitHub Actions wykonuje kontrole po wypchnięciu zmian, w tym testy algorytmu
i sprawdzenie składni wariantu 2.10 w kontenerze Python 2.7.
Kolejny krok po uruchomieniu integracji: porównanie jakości źródeł na rzeczywistych
zdjęciach, potem optymalizacja podglądu i lepsza obsługa dłuższych rys.

Dokumentacja: [wtyczki Python](https://developer.gimp.org/resource/writing-a-plug-in/tutorial-python/),
[Gimp.heal](https://developer.gimp.org/api/3.0/libgimp/func.heal.html).
