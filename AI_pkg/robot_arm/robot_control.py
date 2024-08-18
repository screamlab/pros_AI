import rclpy
import math
import numpy as np
import time
from robot_arm.ik2 import pybulletIK
import cv2
import threading

class RobotArmControl:
    def __init__(self, node):
        self.node = node
        self.current_angle = [
            np.deg2rad(90),
            np.deg2rad(40),
            np.deg2rad(160),
            np.deg2rad(180),
            np.deg2rad(70),
            0,
            0,
            0,
        ]
        self.ik_solver = pybulletIK(self.current_angle)
        self.arm_radians_angle = self.current_angle
        self.depth = None
        self.direction = None
        self.stop_threads_flag = False  # 统一使用一个标志变量来控制所有线程


    def degree_to_radians(self, data):
        return list(np.radians(data))

    def start_depth_monitoring(self):
        def monitor_depth():
            while not self.stop_threads_flag:
                self.depth = self.node.get_object_depth()
                if self.depth is None:
                    self.depth = 100
                time.sleep(0.1)  # 控制深度更新频率

        self.depth_thread = threading.Thread(target=monitor_depth)
        self.depth_thread.start()

    def start_direction_monitoring(self):
        def monitor_direction():
            while not self.stop_threads_flag:
                self.direction = self.node.get_object_direction()
                time.sleep(0.1)  # 控制方向更新频率

        self.direction_thread = threading.Thread(target=monitor_direction)
        self.direction_thread.start()

    def stop_threads(self):
        self.stop_threads_flag = True
        self.depth_thread.join()
        self.direction_thread.join()

    def initial_action(self):
        initial_angles = [
            np.deg2rad(90),
            np.deg2rad(40),
            np.deg2rad(160),
            np.deg2rad(180),
            np.deg2rad(110)
        ]
        self.arm_radians_angle = initial_angles  # 更新当前角度为初始动作角度
        print("initial")
        self.node.publish_arm(initial_angles)
        time.sleep(1)

    def forward_grap(self):
        new_angles = list(self.arm_radians_angle)
        if(new_angles[1] > np.deg2rad(120)):
            self.node.publish_arm([-1, -1, -1, -1, np.deg2rad(5)])
            time.sleep(1)
            print("over")
        else:
            new_angles[1] += np.deg2rad(50)
            new_angles[2] -= np.deg2rad(60.5)
            self.arm_radians_angle = new_angles
            self.node.publish_arm(new_angles)
            time.sleep(2)
            self.node.publish_arm([-1, -1, -1, -1, np.deg2rad(5)])

            time.sleep(2)
            initial_angles = [
                np.deg2rad(90),
                np.deg2rad(30),
                np.deg2rad(160),
                np.deg2rad(180),
                np.deg2rad(10)
            ]
            self.arm_radians_angle = initial_angles  # 更新当前角度为初始动作角度
            self.node.publish_arm(initial_angles)
            time.sleep(1)

    def adjust_angles_based_on_direction(self):
        adjustment_step = np.deg2rad(2)
        adjustment_step2 = np.deg2rad(3)
        new_angles = list(self.arm_radians_angle)

        if self.direction == "left":
            new_angles[0] += adjustment_step
        elif self.direction == "right":
            new_angles[0] -= adjustment_step
        elif self.direction == "up":
            new_angles[2] -= adjustment_step2
            if new_angles[2] < 0:
                new_angles[2] = 0  # 保持在最小值
        elif self.direction == "down":
            new_angles[2] += np.deg2rad(3)
            if new_angles[2] > np.deg2rad(160):
                new_angles[2] -= np.deg2rad(5)  # 保持在最大值
                new_angles[1] += np.deg2rad(2)
                if new_angles[1] > np.deg2rad(180):
                    new_angles[1] = np.deg2rad(180)  # 保持在最大值
        elif self.direction == "front":
            new_angles[1] += np.deg2rad(3)
            new_angles[2] -= np.deg2rad(3)
            if new_angles[1] > np.deg2rad(180):
                new_angles[1] = np.deg2rad(180)  # 保持在最大值
            if new_angles[2] < 0:
                new_angles[2] = 0  # 保持在最小值

        self.arm_radians_angle = new_angles
        self.node.publish_arm(new_angles)
        time.sleep(0.3)

    def perform_linear_interpolation(self, target_angles, steps=10):
        if len(target_angles) < len(self.arm_radians_angle):
            target_angles.extend([0] * (len(self.arm_radians_angle) - len(target_angles)))

        interpolated_angles_array = np.linspace(self.arm_radians_angle, target_angles, steps)
        fixed_angles = [np.deg2rad(180), np.deg2rad(110)]

        mid_index = steps // 2
        interpolated_angles = interpolated_angles_array[mid_index]
        interpolated_angles[3] = fixed_angles[0]
        interpolated_angles[4] = fixed_angles[1]

        self.node.publish_arm(interpolated_angles)
        self.arm_radians_angle = target_angles
        time.sleep(1)

    def position_adjustment(self):
        if self.direction == "left":
            action = "COUNTERCLOCKWISE_ROTATION_SLOW"
            self.node.publish_to_robot(action, pid_control=False)
        elif self.direction == "right":
            action = "CLOCKWISE_ROTATION_SLOW"
            self.node.publish_to_robot(action, pid_control=False)
        else:
            action = "FORWARD_SLOW"
            self.node.publish_to_robot(action, pid_control=False)

    def precision_grap(self):
        while 1:
            action = "STOP"
            self.node.publish_to_robot(action, pid_control=False) # 防止夾取時移動
            if self.depth < 0.25 and self.direction == "front":
                self.forward_grap()
                break
            else:
                self.adjust_angles_based_on_direction()

    def grap(self, tag_name):
        self.initial_action()
        self.node.publish_tag_name("None")
        mission_complete = 1
        see_tag_in_moment = 0
        self.start_depth_monitoring()
        self.start_direction_monitoring()
        while mission_complete:
            self.node.publish_tag_name(tag_name)
            tag_signal = self.node.get_tag_exist_signal()
            if tag_signal != "0":
                see_tag_in_moment += 1
                data = self.node.get_target_pos()
                if self.depth > 0.3:
                    self.position_adjustment()
                    self.adjust_angles_based_on_direction()
                else:
                    action = "STOP"
                    self.node.publish_to_robot(action, pid_control=False)
                    self.precision_grap()
                    time.sleep(2) # 等夾具收回判斷
                    print(tag_signal, self.depth)
                    if tag_signal == "0" or (tag_signal != "0" and self.depth < 0.3) or (tag_signal != "0" and self.depth == 100):
                        print("complete")
                        mission_complete = 0
                        self.stop_threads()
                    else:
                        self.initial_action()
            elif see_tag_in_moment > 2:
                action = "STOP"
                self.node.publish_to_robot(action, pid_control=False)
                see_tag_in_moment = 0
            else:
                action = "COUNTERCLOCKWISE_ROTATION_MEDIAN"
                self.node.publish_to_robot(action, pid_control=False)
        action = "STOP"
        self.node.publish_to_robot(action, pid_control=False)
