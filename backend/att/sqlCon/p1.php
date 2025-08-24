<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<title>CHOKH</title>
 
<script language="javascript" type="text/javascript" src="script.js"></script>
<script>
 $(document).ready(function(){
 setInterval(function(){cache_clear()},100000);
 });
 function cache_clear()
{
 //window.location.reload(true); //use this if you do remove cache
  window.location.reload(); 
}
</script> 
</head>
<?php	
$dbName = "C:/Program Files (x86)/HAMS-19/HAMS_2025.mdb";
$dbName_zk = "C:/Program Files (x86)/ZKTeco/att2000.mdb";

if (!file_exists($dbName)) {
    die("Could not find database file.");
}
$db = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName; Uid=; Pwd=;");
$db_zk = new PDO("odbc:DRIVER={Microsoft Access Driver (*.mdb)}; DBQ=$dbName_zk; Uid=; Pwd=;");

include("database1.php");
$lDate=date('Y-m-d', strtotime("-5 day", strtotime(date("Y-m-d"))));
$lDate=date('Y-m-d', strtotime("-10 day", strtotime(date("Y-m-d"))));

$sl=0; 
$sql  = "SELECT *, Format(eventDate,'YYYY-MM-DD') as myDate from pubEvent where eventCard<>'' and Format(eventDate,'YYYY-MM-DD')>'$lDate' and eventCode in('09', '00') order by eventDate";
$result = $db->query($sql);
while ($row = $result->fetch()) {
 
$logDate=date("Y-m-d", strtotime($row["eventDate"]));
$logTime=date("H:i:s", strtotime("-10 minutes", strtotime($row['eventTime'])));
//strtotime("+15 minutes", strtotime($selectedTime));
$userId=$row['eventCard'];
$accessDevice=$row['deviceID'];
$accessDoor=$row['doorName'];

$sl++;
$q=mysql_query("insert into  att_raw_data values('null', '$logDate', '$userId', '$userId', '', '$logTime', '0', '$accessDoor', '', '$accessDevice')");
//if(!$q)
//echo "Error! ID: ".$userId;
}

echo "Fetched " .$sl. " Record(s) from HAMS Devices";
echo "<br><br>";

$slZK=0;

$sql  = "SELECT * from CHECKINOUT t1 left join USERINFO t2 on t2.USERID=t1.USERID where Format(CHECKTIME,'YYYY-MM-DD')>'$lDate' order by CHECKTIME";
$result = $db_zk->query($sql);
while ($row = $result->fetch()) {
$logDate=date("Y-m-d", strtotime($row["CHECKTIME"]));
$logTime=date("H:i:s", strtotime("-10 minutes", strtotime($row['CHECKTIME'])));
//strtotime("+15 minutes", strtotime($selectedTime));
$userId=$row['Badgenumber'];
//if($row['sn']=='A8N5232360667')
//echo $userId."---".$logDate."---".$logTime."<br>";
if(strlen($userId)>4)
	continue;

//echo $userId;
//echo "<br>";
$accessDevice='ZKT-'.$row['sn'];
$accessDoor=$row['sn'];
$slZK++;

//$sql1  = "SELECT * from USERINFO where USERID='$userId'";
//$result1 = $db_zk->query($sql1);
//$row1 = $result1->fetch();

//echo $empId=$result['badgenumb'];


$str="insert into  att_raw_data values('null', '$logDate', '$userId', '$userId', '', '$logTime', '0', '$accessDoor', '', '$accessDevice')";
mysql_query($str);
//if(!$q)
//echo "Error! ID: ".$userId;

}

echo "Fetched " .$slZK. " Record(s) from ZKT Devices";