<p class="form__headline"> </p> 


<div class="form__fields-wrapper"> 

<div class="form__group form__group--double form__group--light form__group--big">
  [text* your-name class:form__input class:form__input--darkmode]
  <label class="form__label form__label--absolute form__label--icon form__label--icon-user form__label--icon-turquoise form__label--turquoise-active">Imię i nazwisko*<span class="form__label-star"></span></label>
</div>



<div class="form__group form__group--double form__group--light form__group--big">
  [email* your-email class:form__input class:form__input--darkmode ]
  <label class="form__label form__label--absolute form__label--icon form__label--icon-envelope form__label--icon-turquoise form__label--turquoise-active">Adres e-mail*<span class="form__label-star"></span></label>
</div>

<div class="form__group form__group--double form__group--light form__group--big">
  [tel* tel-660 class:form__input class:form__input--darkmode ]
  <label class="form__label form__label--absolute form__label--icon form__label--icon-phone form__label--icon-turquoise form__label--turquoise-active">Numer telefonu*<span class="form__label-star"></span></label>
</div>

<div class="form__group form__group--double form__group--light form__group--textarea">
  [textarea your-message 30x7 class:form__input class:form__input--darkmode ]
  <label class="form__label form__label--absolute form__label--icon form__label--icon-pen form__label--icon-turquoise form__label--turquoise-active form__label--textarea">Jeśli chcesz, dodaj komentarz</label>
  <p class="form__counter"> 0 / 1000 znaków</p>
</div>



<p class="form__data-controller">Twoje dane osobowe przetwarzane są do celów takich jak komunikacja w sprawie oferty zgodnie z <a href="https://coaction.pl/polityka-prywatnosci/" class="form__data-controller-link">polityką prywatności.</a></p>

<button type="submit" class="btn btn--xl btn--send btn--icon btn--icon-paper-plane-top btn--style-cta">Wysyłam wiadomość</button></div>

[hidden utm_source]
[hidden utm_medium]
[hidden utm_campaign]
[hidden utm_term]
[hidden utm_content]
[hidden utm_id]
[hidden utm_source_platform]

[hidden referrer]
[hidden landing_page]
[hidden device]

[hidden gbraid]
[hidden wbraid]


///// OLD

<label> Your name
    [text* your-name autocomplete:name] </label>

<label> Your email
    [email* your-email autocomplete:email] </label>

<label> Subject
    [text* your-subject] </label>

<label> Your message (optional)
    [textarea your-message] </label>

[submit "Submit"]