Lista zmian do nocodb 

Companies 

communication_processes, business_impact 

 – nie jest to jasne, dodać field description jaki tam input robić. 

LEADS 

contact_name – zamieniłabym na lead_name, skoro tutaj są zarówno firmy jak i klienci B2B 

type – uściślałabym na wszelki wypadek, bo może się to przydać przy pracy z różnymi tabelami, gdzie co chwila są type i variant - to może się mylić. Tutaj chyba ok byłby: lead_type 

source też może być lead_source 

value – deal_value ( w description dodać „wartość szansy sprzedaży”) 

contact_channel – ok, ale brakuje typów kontaktu, zobacz tabelkę poniżej: 

Źródło 

Kolumna1 

Google 

 

Outreach 

 

Existing client 

klient który płynnie kontynuuje lub kupuje nowa usługę 

Linked In 

 

Recommendation 

 

Webinar 

 

Facebook 

 

Coming back Lead 

ktoś kto był w procesie zakupu ale NIE kupił 

Coming back Client 

ktoś kto kupił kiedyś i wrócił 

 

qualification – z perspektywy marketingowosprzedażowej dobrze mieć jeszcze rozdzielenie na non-mql i non-sql, żeby widzieć na pierwszy rzut oka na jakim etapie byli dyskwalifikowani(np. czy nie było wystarczających danych, żeby się skontaktować -non-mql lub np. czy lead był słabej jakości, więc nie zamienił się w sql). tak mamy obecnie w excelu. 

Uwzględnij proszę wszystkie rodzaje contact_channel z excelowego crm: Bookings Telefon Linkedin CoAction Mail Formularz Facebook Przemka Facebook CoAction Linkedin Przemka 

Rodzaje industry takie jak mamy obecnie w CRM: 

Agriculture 

AI 

Automation 

Automotive 

Banking 

Clothing 

Construction 

Data Solutions 

Design 

E.commerce 

Energy 

Entertainment 

Finance 

Food 

Furniture 

Home Appliances 

Hotels 

HR services 

Insurance 

Networks/Itadmin 

IT, Medicine 

Law 

Machinery 

Marketing Agency 

Media 

Medicine 

Medicine, Pharma 

Military 

Packaging 

Pharma 

Public sector 

Publishing 

Real Estate 

Retail 

Software Development 

Tech Product 

Telecommunication 

Tourism 

Training 

Transport/Logistics 

Housing  

Space 

Manufacturing 

Education 

CyberSec 

projects 

Wewnętrzne - zmiana na: coreteam 

PARTICIPANTS 

Na uczestników naszych kursów często mówimy participants. Jeśli dobrze rozumiem w tej tabeli są uczestnicy spotkań, np. osoby audytowane. Nie każda osoba audytowana zostanie uczestnikiem kursu dlatego zmieniłabym na attendees. 

Meetings 

type – meeting_type 

Dobrze byłoby dodać do pól field descriptions z opisem jaki tu ma być input i gdzie trafi w prezentacji, bo po samych nazwach jest to niejasne 

Assesments 

ai_status w description powinna być wskazówka co zrobić, żeby wygenerować treść – np. po uzupełnieniu powyższych pól zmień status na x, odśwież i wtedy zobaczysz wygenerowany plik. 

Recommendations 

priority – brakuje wyjaśnienia czego to jest priorytet 

ai_status w field description powinna być króciutka informacja o procesie jak to wygenerować. 

Training_moduleS 

nazwę tabeli TRAINING_MODULES chyba jest sens zmienić na Training_descriptions 

category – Training_Type 

goal_statement – learning_goal 

hours_in_package 

recommendation_items – recommendation_packages 

Recommendation_items 

Nazwa tabeli: recommendation_packages, a nie items 

label – chyba package_name 

hours – Hours_in_Package 

mode – Training_Group_Size 

 

pricing 

segment – product 

mode – Training_Group_Size 

price – (total_price vs hourly price) 

Testimonials 

do dodania do industry – rozróznienie IT na data, software, AI, cybersecurity 

Offers 

price zmienić na – total price (versus hourly price) 

data-json – powinny być description co tutaj się wypełnia, a jeśli tego nie ruszać to też można to zaznaczyć w opisie 

warnings - – powinny być description co tutaj się wypełnia 

variant – product_type (dodać trzeba jeszcze Audyt językowy, Job Interview, Webinar) – tutaj powinno dać się wybrać kilka, bo w jednej ofercie może być kilka różnych. 