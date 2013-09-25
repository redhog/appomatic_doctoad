jQuery(document).ready(function() {
  window.Showdown.extensions.change = function(converter) {
    return [
        { type: 'lang', regex: '&lt;&lt;&lt;&lt;&lt;&lt;&lt; (.*)', replace: function(match, name) {
        return "&lt;&lt;&lt;&lt;&lt;&lt;&lt;" + name + "<br>";
      }},
      { type: 'lang', regex: '<<<<<<< (.*)', replace: function(match, name) {
        return "&lt;&lt;&lt;&lt;&lt;&lt;&lt; " + name + "<br>";
      }},
      { type: 'lang', regex: '=======', replace: function(match) {
        return "=======<br>";
      }},
      { type: 'lang', regex: '&gt;&gt;&gt;&gt;&gt;&gt;&gt; (.*)', replace: function(match, name) {
        return "&gt;&gt;&gt;&gt;&gt;&gt;&gt; " + name + "<br>";
      }},
      { type: 'lang', regex: '>>>>>>> (.*)', replace: function(match, name) {
        return "&gt;&gt;&gt;&gt;&gt;&gt;&gt; " + name + "<br>";
      }},
      { type: 'lang', regex: '\\[-', replace: function(match) {
        return '<span class="removed">';
      }},
      { type: 'lang', regex: '-\\]', replace: function(match) {
        return '</span>';
      }},
      { type: 'lang', regex: '\\{\\+', replace: function(match) {
        return '<span class="added">';
      }},
      { type: 'lang', regex: '\\+\\}', replace: function(match) {
        return '</span>';
      }}
    ];
  };

  var markdownize = function(content) {
    var html = content.split("\n").map($.trim).filter(function(line) { 
      return line != "";
    }).join("\n");
    return toMarkdown(html);
  };

  var converter = new Showdown.converter({extensions:["change"]});
  var htmlize = function(content) {
    return converter.makeHtml(content);
  };

  // Enable Hallo editor
  jQuery('.editable').hallo({
    plugins: {
      'halloformat': {},
      'halloheadings': {},
      'hallolists': {},
      'halloreundo': {}
    },
    toolbar: 'halloToolbarFixed'
  });

  jQuery('.editable').each(function () {
    var editable = $(this);
    var source = $("#" + this.id + "_source");

    // Method that converts the HTML contents to Markdown
    var showSource = function(content) {
      var markdown = markdownize(content);
      if (source.get(0).value == markdown) {
        return;
      }
      source.get(0).value = markdown;
    };


    var updateHtml = function(content) {
      if (markdownize(editable.html()) == content) {
        return;
      }
      var html = htmlize(content);
      editable.html(html); 
    };

    // Update Markdown every time content is modified
    editable.bind('hallomodified', function(event, data) {
      showSource(data.content);
    });
    source.bind('keyup', function() {
      updateHtml(this.value);
    });
    updateHtml(source.val());
  });

  jQuery('.viewable').each(function () {
    var viewable = $(this);
    viewable.html(htmlize(viewable.html()));
  });

    $(".popover-trigger").popover({html:true, placement: "bottom"});
}); 
