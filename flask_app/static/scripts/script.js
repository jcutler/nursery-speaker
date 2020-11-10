function preloader() {
    var nodes = {
        'white': document.createElement('div'),
        'black': document.createElement('div'),
        'blue': document.createElement('div'),
        'grey': document.createElement('div')
    };
    
    var body = document.getElementsByTagName('body')[0];
    
    Object.keys(nodes).forEach(function(key) {
        nodes[key].style.background = "url(" + window.static_root + "/spinner-" + key + ") no-repeat -9999px -9999px;";
        nodes[key].style.position = "absolute";
        nodes[key].style.top = "-1px";
        body.appendChild(nodes[key]);
    });
}

function setEnabled(enable, btn=null) {
    var btns = document.getElementsByTagName('button');
    var spinners = document.getElementsByClassName('spinner');
    
    if (enable) {
        Object.keys(spinners).forEach(function(key) {
            spinners[key].style.display = "none";
        });
    }
    
    Object.keys(btns).forEach(function(key) {
        btns[key].disabled = !enable;
        if (btns[key] !== btn) {
            if (enable) {
                btns[key].classList.remove('disabled');
            } else {
                btns[key].classList.add('disabled');
            }
        }
    });
}

function doCommand(btn, data) {
    btn.getElementsByClassName('spinner')[0].style.display = "block";
    setEnabled(false, btn);
    
    Object.keys(data).forEach(function(key){
        if (['mode', 'level'].indexOf(key) < 0) {
            delete data[key];
        }
    });
    
    var queryString = Object.keys(data).map(function(key) {
        return key + '=' + data[key]
    }).join('&');

    var xhr = new XMLHttpRequest();
    xhr.open('POST', 'server', true);

    xhr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            setEnabled(true);
            if (xhr.status === 401) {
                window.location.reload();
            }
            else if (xhr.status !== 201) {
                window.alert("Error Encountered");
                console.log(xhr.status);
                console.log(xhr.responseText);
            } else {
                console.log(JSON.parse(xhr.responseText));
            }
        }
    }
    
    xhr.send(queryString);
}

function setup() {
    btns = document.getElementsByTagName('button');
    Object.keys(btns).forEach(function(key) {
        btns[key].onclick = function() {
            doCommand(btns[key], this.dataset);
        };
    });
}

window.onload = function() {
    preloader();
    setup();
}
