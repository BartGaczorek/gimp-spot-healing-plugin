# GIMP Spot Healing Plugin

Eksperymentalna wtyczka do retuszu drobnych skaz jednym kliknięciem.
Źródło jest dobierane automatycznie z otoczenia, a naprawę wykonuje **Healing
GIMP-a** — z dopasowaniem przejścia, zamiast prostego wklejania pikseli.

## Status: prototyp 0.1 — do pierwszej próby w GIMP-ie

Kod przeznaczony dla **GIMP-a 3.x**, Python 3 / GTK 3 dostarczanych z GIMP-em.
Nie jest zgodny z GIMP-em 2.10. Nie wymaga NumPy, OpenCV ani Resynthesizera.
Testy automatyczne obejmują dobór źródła i geometrię widoku. Uruchomienie okna,
wywołania GIMP/GEGL i jakość retuszu wymagają jeszcze sprawdzenia w działającym
GIMP-ie; nie zostały przetestowane w środowisku, w którym powstała ta wersja.

## Instalacja

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
| Zachowanie retuszu | Zastosuj; kopia zostaje w dokumencie |
| Odrzucenie sesji | Anuluj / zamknięcie okna; kopia jest usuwana |

Ustaw pędzel tylko trochę większy od skazy. Włos zamaluj krótkim ruchem
wzdłuż jego przebiegu. Zbyt duży pędzel lub zbyt długi ruch utrudniają znalezienie
pasującego źródła. Nie ma automatycznego wykrywania całego włosa po jednym kliknięciu.

## Jak działa wersja 0.1

1. Otacza wskazany obszar granicą próbkowania; wnętrze skazy nie jest używane do
   porównywania źródeł.
2. Sprawdza do 160 przesunięć w odległości do sześciu średnic pędzla. Cały
   prostokąt potencjalnego źródła musi być rozłączny z prostokątem naprawy.
3. Porównuje próbki otoczenia, uwzględniając różnicę koloru i dopasowanie tekstury
   po odjęciu stałej różnicy jasności/koloru. Odrzuca próbkowaną przezroczystość.
4. Wywołuje natywne `Gimp.heal` z wybranym źródłem. Krótki ruch zachowuje jeden
   offset źródła na całej długości, aby ograniczyć niespójności między punktami.
5. Cofnięcie odtwarza piksele zapisane w formacie warstwy, bez sprowadzania ich
   do 8 bitów. Bufor 8-bitowy służy do podglądu i oceny źródeł, nie do naprawy.

To heurystyczny dobór próbki, a nie semantyczne rozpoznawanie obrazu. Może wybrać
nieodpowiednią teksturę obok krawędzi, innych skaz lub skomplikowanych wzorów.
Wtedy cofnij i spróbuj mniejszego pędzla / krótszego ruchu. Algorytm nie obiecuje
usunięcia każdej skazy ani automatycznego zabezpieczenia wszystkich detali.

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
cofnięcie, cofnięcie całego ruchu, Anuluj i Zastosuj. Potem sprawdź zdjęcie 16-bitowe
i komunikat o braku obsługi warstwy przesuniętej względem płótna.

Do zgłoszenia dodaj system, pełną wersję GIMP-a, rozmiar i precyzję obrazu,
średnicę pędzla, kroki odtworzenia oraz dokładny komunikat. Jeśli to możliwe,
dołącz niesensytywny wycinek zdjęcia przed i po naprawie.

## Rozwój

```sh
python -m unittest discover -s tests -v
python -m compileall -q gimp-spot-heal
```

GitHub Actions wykonuje te same kontrole po wypchnięciu zmian.
Kolejny krok po uruchomieniu integracji: porównanie jakości źródeł na rzeczywistych
zdjęciach, potem optymalizacja podglądu i lepsza obsługa dłuższych rys.

Dokumentacja: [wtyczki Python](https://developer.gimp.org/resource/writing-a-plug-in/tutorial-python/),
[Gimp.heal](https://developer.gimp.org/api/3.0/libgimp/func.heal.html).
