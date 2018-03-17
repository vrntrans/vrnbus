/*редирект на заданную страницу*/
function redirect(page){
    var url = document.location.href.split("/");
    var redirect = "";
    for (var i = 0; i <= url.length - 2; i++){
        redirect +=url[i]+"/";
    }
    document.location.href = redirect+page;
}
/*удаление сессии*/
function logout(name){
    document.cookie = name + "=" + "; expires=Thu, 01 Jan 1970 00:00:01 GMT";
    var url = document.location.href.split("/");
    var redirect = "";
    for (var i = 0; i <= url.length - 2; i++){
        redirect +=url[i]+"/";
    }
    document.location.href = redirect;
}
/*обновление страницы*/
function fresh() {
    location.reload();
}

//проверка ответа сервера
function checkResponseServer(response){
    //строковые константы для ответа
    var SERVER_ERROR = 'Потеряно соединение с сервером';
    var EMPTY_RESPONSE = 'Данные пусты';
    if (response.responseText === undefined || response.responseText === null){
        return SERVER_ERROR;
    }
    if (response.responseText.length-1 === 0 || response.responseText === "[]" || response.responseText === ""){
        return EMPTY_RESPONSE;
    }
}


//приводит время к правильному виду
function parseTime(time){
    time.getHours() < 10? hour = "0" + time.getHours() : hour = time.getHours();
    time.getMinutes() < 10? min = "0" + time.getMinutes() : min = time.getMinutes();
    time = hour + ":" + min + ":00";
    return time;
}

function temp(x){
    x = x.toString();
    var one = x.substr(0,2);
    var two = x.substr(2,2);
    return one + "."+two;
}