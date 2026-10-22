<h2 id="talks">Talks &amp; Conferences</h2>

<div class="publications">
<ol class="bibliography" style="margin: 0; padding-left: 18px;">
{% for talk in site.data.talks.main %}
<li style="margin-bottom: 14px;">
  <div class="pub-row">
    <div class="col-sm-12" style="position: relative; padding-right: 0; padding-left: 0;">
      <div class="title" style="margin: 0 0 2px 0; line-height: 1.25;">
        <a href="{{ talk.slides | relative_url }}" target="_blank" rel="noopener">{{ talk.title | escape }}</a>
      </div>
      {% if talk.subtitle %}
      <div style="margin: 0 0 2px 0; line-height: 1.35;">{{ talk.subtitle | escape }}</div>
      {% endif %}
      <div class="periodical" style="margin: 0 0 4px 0; line-height: 1.35;">
        <em>{{ talk.event | escape }}</em><br>
        {{ talk.location | escape }} &middot; {{ talk.date | escape }}
      </div>
      <div class="links" style="margin: 0;">
        <a href="{{ talk.slides | relative_url }}" class="btn btn-sm z-depth-0" role="button" target="_blank" rel="noopener" style="font-size:12px; padding: 1px 6px;">Slides</a>
      </div>
    </div>
  </div>
</li>
{% endfor %}
</ol>
</div>
