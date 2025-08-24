<?php
$dbName_zk = "D:/ABEDY/attendance-system/backend/att2000.mdb";

// Check if Access DB exists
if (!file_exists($dbName_zk)) {
    die("Could not find Access database file.");
}

// Connect to Access via ODBC
try {
	$db_zk = new PDO("odbc:Driver={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=$dbName_zk;");
    $db_zk->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    die("Access connection failed: " . $e->getMessage());
}

// Include MySQL connection
include("database1.php");

// Check MySQL connection
if (!$mylink) {
    die("MySQL connection failed: " . mysqli_connect_error());
}

// Date filter
$lDate = date('Y-m-d', strtotime("-10 days"));

// Fetch logs from Access DB
$sql = "SELECT * FROM CHECKINOUT t1 
        LEFT JOIN USERINFO t2 ON t2.USERID = t1.USERID 
        WHERE Format(CHECKTIME,'YYYY-MM-DD') > ? 
        ORDER BY CHECKTIME";

try {
    $stmt_access = $db_zk->prepare($sql);
    $stmt_access->execute([$lDate]);
} catch (PDOException $e) {
    die("Access query failed: " . $e->getMessage());
}

$slZK = 0;

while ($row = $stmt_access->fetch(PDO::FETCH_ASSOC)) {
    $logDate = date("Y-m-d", strtotime($row["CHECKTIME"]));
    $logTime = date("H:i:s", strtotime("-10 minutes", strtotime($row['CHECKTIME'])));
    $userId = $row['Badgenumber'];

    if (strlen($userId) > 4) continue;

    $accessDevice = 'ZKT-' . $row['sn'];
    $accessDoor = $row['sn'];
    $slZK++;

    // Insert into MySQL using prepared statement
    $insert_sql = "INSERT INTO att_raw_data 
        (id, log_date, user_id, badgenumber, something, log_time, status, access_door, something2, access_device) 
        VALUES (NULL, ?, ?, ?, '', ?, 0, ?, '', ?)";
    
    $stmt_mysql = mysqli_prepare($mylink, $insert_sql);
    if (!$stmt_mysql) {
        echo "MySQL prepare failed for user $userId: " . mysqli_error($mylink) . "<br>";
        continue;
    }

    mysqli_stmt_bind_param($stmt_mysql, "ssssss", $logDate, $userId, $userId, $logTime, $accessDoor, $accessDevice);

    if (!mysqli_stmt_execute($stmt_mysql)) {
        echo "Insert failed for user $userId: " . mysqli_stmt_error($stmt_mysql) . "<br>";
    }

    mysqli_stmt_close($stmt_mysql);
}

echo "Fetched " . $slZK . " Record(s) from ZKT Devices";
?>
