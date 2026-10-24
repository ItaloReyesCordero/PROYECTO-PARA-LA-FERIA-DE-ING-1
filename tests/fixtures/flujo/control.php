<?php

function nota(int $n): string
{
    if ($n >= 18) {
        return "excelente";
    } elseif ($n >= 14) {
        return "bueno";
    } elseif ($n >= 11) {
        return "aprobado";
    } else {
        echo "desaprobado\n";
    }
    $i = 0;
    do {
        $i++;
    } while ($i < 3);
    foreach ([1, 2, 3] as $k => $v) {
        if ($v === 2) {
            continue;
        }
        echo $k;
    }
    return "fin";
}
