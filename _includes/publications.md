<h2 id="publications" style="margin: 2px 0px -15px;">Publications (alphabetical order)</h2>

<div class="publications">
<ol class="bibliography" style="margin: 0; padding-left: 18px;">

{% for link in site.data.publications.main %}

<li style="margin-bottom: 14px;">
  <div class="pub-row">
    <div class="col-sm-12" style="position: relative; padding-right: 0; padding-left: 0;">
      <div class="title" style="margin: 0 0 2px 0; line-height: 1.25;">
        <a href="{{ link.pdf }}">{{ link.title }}</a>
      </div>
      <div class="author" style="margin: 0 0 2px 0; line-height: 1.35;">
        {{ link.authors }}
      </div>
      {% if link.conference %}
      <div class="periodical" style="margin: 0 0 4px 0; line-height: 1.35;">
        <em>{{ link.conference }}</em>
      </div>
      {% endif %}
      <div class="links" style="margin: 0;">
        {% if link.pdf %}
        <a href="{{ link.pdf }}" class="btn btn-sm z-depth-0" role="button" target="_blank" style="font-size:12px; padding: 1px 6px;">PDF</a>
        {% endif %}
        {% if link.code %}
        <a href="{{ link.code }}" class="btn btn-sm z-depth-0" role="button" target="_blank" style="font-size:12px; padding: 1px 6px;">Code</a>
        {% endif %}
        {% if link.page %}
        <a href="{{ link.page }}" class="btn btn-sm z-depth-0" role="button" target="_blank" style="font-size:12px; padding: 1px 6px;">Project Page</a>
        {% endif %}
        {% if link.bibtex %}
        <a href="{{ link.bibtex }}" class="btn btn-sm z-depth-0" role="button" target="_blank" style="font-size:12px; padding: 1px 6px;">BibTex</a>
        {% endif %}
        {% if link.notes %}
        <strong><i style="color:#e74d3c">{{ link.notes }}</i></strong>
        {% endif %}
        {% if link.others %}
        {{ link.others }}
        {% endif %}
      </div>
    </div>
  </div>
</li>

{% endfor %}

</ol>
</div>
